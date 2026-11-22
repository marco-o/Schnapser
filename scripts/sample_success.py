"""Played success rates of the Basic bot, per hand mask and seat.

  scripts/run_py.sh scripts/sample_success.py [--games 4096] [--target 10]

Unlike game/success_table.json (the networks' value-head *estimates*), this
plays deals out. Random deals as at the table: Basic chooses trump from the
Caller's first three cards; then each game below forces its bidding (the
declarer calls, everyone else passes) and Basic plays all four seats.

  normal             everyone passes
  schnapser_caller   the Caller (game seat 0) calls Schnapser
  schnapser_partner  the Caller's partner (seat 2) calls Schnapser
  lomt               each seat in turn calls Lomt; a seat without an As
                     fails without playing
  bauern             the seat holding the trump As calls Bauern; every
                     other seat fails without playing

Index. A result is filed under (mask, seat): the hand's mask is the success
table's class key (game/success.py class_key: the four suit rank masks, bit
r = rank r held, ranks Unter..As; trump first, the rest descending; no trump
in a Lomt), and seat is the game seat (the Caller is 0).

  normal, schnapser_*  every seat's index: (its mask, its seat)
  lomt, bauern         the declarer's index; Lomt always with seat 0 (the
                       declarer leads, so the seat does not matter)

Each index keeps [samples, wins]. A win is the seat's pair winning in the
Normal game, and the contract being made otherwise (also for a defender's
index in a Schnapser: there it reads "how often the Schnapser is made
against this hand").

Once every index of a game has --target samples, that game is not played
for that deal; otherwise it is played and every one of its indexes counts
the result. Results add up over runs in data/played_success.json, saved
every --save-every games; run again (a higher --target gives more samples).
"""

import argparse
import json
import os
import sys
import time

import jax
import jax.numpy as jnp
import numpy as np

from open_spiel.python.jax.games import schnaps as G
from open_spiel.python.scale.ckpt import artifact
from open_spiel.python.scale.core import types
from open_spiel.python.scale.core import x64
from open_spiel.python.scale.envs import schnaps as schnaps_env

from schnaps_web.game import player as _site_player  # registers the arch  # noqa: F401
from schnaps_web.game import success as success_lib

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(SITE, "models", "basic_player")
OUT = os.path.join(SITE, "data", "played_success.json")
SCHEMA = "schnaps-web-played-success/2"
GAMES = ("normal", "schnapser_caller", "schnapser_partner", "lomt", "bauern")
AS = G.NUM_RANKS - 1
MAX_STEPS = 7 + 20  # bids, cards (trump is chosen when dealing)


class Sampler:
  """Basic in all four seats, batched; deals and forced playouts."""

  def __init__(self, batch: int):
    x64.enable_x64()
    art = artifact.load_artifact(MODEL, 0)
    self.policy, self.params = art.policy, art.params
    self.batch = batch
    env = schnaps_env.SchnapsEnv()
    vinfo = jax.vmap(env.info_state)
    vlegal = jax.vmap(env.legal_mask)
    vactor = jax.vmap(env.actor)
    vterm = jax.vmap(env.terminal)
    vstep = jax.vmap(env.step)

    def greedy(s, key):
      """Basic's argmax move for each row's actor."""
      seats = jnp.maximum(vactor(s), 0)
      legal = vlegal(s)
      b = seats.shape[0]
      step = types.SeatStep(
          info=vinfo(s, seats),
          legal_mask=legal,
          seat=seats,
          to_move=seats,
          new_hand=jnp.zeros((b,), jnp.bool_),
          new_match=jnp.zeros((b,), jnp.bool_),
          last_action=jnp.full((b,), types.NO_ACTION, jnp.int32),
          last_actor=jnp.full((b,), types.NO_ACTOR, jnp.int32),
      )
      carry = self.policy.init_carry(self.params, b, seats, key)
      out = self.policy.evaluate(self.params, carry, step, key)
      return jnp.argmax(jnp.where(legal, out.logits, -jnp.inf), axis=-1).astype(jnp.int32)

    def deal(k1, k2):
      """Random deals up to the first bid (Basic chooses trump)."""
      s = jax.vmap(env.init)(k1)
      return vstep(s, greedy(s, k1[0]), k2)

    def play(s, declarer, call, key):
      """Forced bids (the declarer calls, the rest pass), then Basic plays."""
      b = s.phase.shape[0]

      def body(carry):
        s, i = carry
        a = greedy(s, key)
        me = vactor(s) == declarer
        forced = jnp.where(me & (s.contract == G.NORMAL) & (call >= 0), call, G.PASS_ACTION)
        a = jnp.where(s.phase == G.PHASE_BIDDING, forced, a)
        done = vterm(s)
        nxt = vstep(s, jnp.where(done, 0, a), jax.random.split(key, b))
        keep = lambda x, y: jnp.where(done.reshape((b,) + (1,) * (x.ndim - 1)), x, y)  # noqa: E731
        return jax.tree.map(keep, s, nxt), i + 1

      def cond(carry):
        s, i = carry
        return (i < MAX_STEPS) & ~jnp.all(vterm(s))

      s, _ = jax.lax.while_loop(cond, body, (s, jnp.int32(0)))
      return jax.vmap(env.returns)(s), vterm(s), s.contract

    self._deal = jax.jit(deal)
    self._play = jax.jit(play)

  def deals(self, key):
    """`batch` random deals at the first bid: (states, holder, trump)."""
    k = jax.random.split(key, 2 * self.batch)
    s = self._deal(k[: self.batch], k[self.batch :])
    assert bool(jnp.all(s.phase == G.PHASE_BIDDING)), "a deal did not reach the bidding"
    return s, np.asarray(s.holder), np.asarray(s.trump)

  def play(self, s, rows, declarers, contract, key):
    """Plays `rows` of s, row i declared by declarers[i]: returns [n, 4]."""
    call = -1 if contract == G.NORMAL else G.FIRST_CALL_ACTION + contract - 1
    pad = self.batch - len(rows)
    idx = np.asarray(list(rows) + [rows[-1]] * pad)
    dec = np.asarray(list(declarers) + [declarers[-1]] * pad, np.int32)
    sub = jax.tree.map(lambda x: x[idx], s)
    ret, term, con = self._play(sub, jnp.asarray(dec), jnp.int32(call), key)
    assert bool(jnp.all(term)), "a playout did not finish"
    assert bool(jnp.all(np.asarray(con) == contract)), "the forced contract was not played"
    return np.asarray(ret)[: len(rows)]


def load(path):
  if os.path.exists(path):
    with open(path) as f:
      data = json.load(f)
    if data.get("schema") != SCHEMA:
      raise ValueError(f"{path}: schema {data.get('schema')!r} is not {SCHEMA}")
    return data
  return {
      "schema": SCHEMA,
      "bot": "basic",
      "about": __doc__.split("Index.")[1].split("Results add up")[0].strip(),
      "next_seed": 0,
      "runs": [],
      # game -> "mask@seat" -> [samples, wins]
      "games": {g: {} for g in GAMES},
  }


def save(path, data):
  os.makedirs(os.path.dirname(path), exist_ok=True)
  tmp = path + ".tmp"
  with open(tmp, "w") as f:
    json.dump(data, f, separators=(",", ":"))
  os.replace(tmp, path)


def main():
  p = argparse.ArgumentParser()
  p.add_argument("--games", type=int, default=4096, help="deals to play")
  p.add_argument("--target", type=int, default=10)
  p.add_argument("--batch", type=int, default=256)
  p.add_argument("--save-every", type=int, default=256)
  p.add_argument("--out", default=OUT)
  a = p.parse_args()
  if a.save_every % a.batch:
    raise SystemExit("--save-every must be a multiple of --batch")

  data = load(a.out)
  sampler = Sampler(a.batch)
  tables = data["games"]
  run = {"target": a.target, "started": time.strftime("%Y-%m-%d %H:%M:%S"),
         "games": 0, "played": {g: 0 for g in GAMES},
         "failed_unplayed": {"lomt": 0, "bauern": 0}, "skipped": {g: 0 for g in GAMES},
         "seconds": 0}
  data["runs"].append(run)
  t0 = time.time()

  def cell(game, mask, seat):
    return tables[game].setdefault(f"{mask}@{seat}", [0, 0])

  while run["games"] < a.games:
    seed = data["next_seed"]
    data["next_seed"] = seed + 1
    key = jax.random.key(seed)
    s, holder, trump = sampler.deals(key)
    n = len(holder)
    hands = [[np.flatnonzero(h == seat).tolist() for seat in range(4)] for h in holder]
    marked = [[success_lib.class_key(h[seat], int(t), True) for seat in range(4)]
              for h, t in zip(hands, trump)]
    plain = [[success_lib.class_key(h[seat], None, False) for seat in range(4)] for h in hands]

    # Each game: [(row, declarer, [(index game, mask, seat), ...])] to play.
    todo = {g: [] for g in GAMES}
    pending = {}

    def wants(game, idxs):
      """Whether some index is short of the target (playouts chosen so far count)."""
      return any(tables[game].get(f"{m}@{x}", [0, 0])[0] + pending.get((game, m, x), 0) < a.target
                 for m, x in idxs)

    def choose(game, row, declarer, idxs):
      if wants(game, idxs):
        todo[game].append((row, declarer, idxs))
        for m, x in idxs:
          pending[(game, m, x)] = pending.get((game, m, x), 0) + 1
      else:
        run["skipped"][game] += 1

    for r in range(n):
      every = [(marked[r][seat], seat) for seat in range(4)]
      choose("normal", r, -1, every)
      choose("schnapser_caller", r, 0, every)
      choose("schnapser_partner", r, 2, every)
      for seat in range(4):
        idx = [(plain[r][seat], 0)]
        if any(c % G.NUM_RANKS == AS for c in hands[r][seat]):
          choose("lomt", r, seat, idx)
        elif wants("lomt", idx):  # no As: failed, not played
          cell("lomt", *idx[0])[0] += 1
          run["failed_unplayed"]["lomt"] += 1
      owner = int(holder[r][int(trump[r]) * G.NUM_RANKS + AS])
      for seat in range(4):
        idx = [(marked[r][seat], seat)]
        if seat == owner:
          choose("bauern", r, seat, idx)
        elif wants("bauern", idx):  # no trump As: failed, not played
          cell("bauern", *idx[0])[0] += 1
          run["failed_unplayed"]["bauern"] += 1

    contracts = {"normal": G.NORMAL, "schnapser_caller": G.SCHNAPSER,
                 "schnapser_partner": G.SCHNAPSER, "lomt": G.LOMT, "bauern": G.BAUERN}
    for gi, game in enumerate(GAMES):
      jobs = todo[game]
      for j in range(0, len(jobs), a.batch):
        chunk = jobs[j : j + a.batch]
        ret = sampler.play(s, [c[0] for c in chunk], [c[1] for c in chunk],
                           contracts[game], jax.random.fold_in(key, 100 * gi + j))
        for (row, declarer, idxs), out in zip(chunk, ret):
          for m, x in idxs:
            c = cell(game, m, x)
            c[0] += 1
            if game == "normal":
              won = out[x] > 0  # the seat's pair won (x is the real seat)
            else:
              won = out[declarer] > 0  # the contract was made
            c[1] += int(won)
        run["played"][game] += len(chunk)

    run["games"] += n
    run["seconds"] = round(time.time() - t0)
    if run["games"] % a.save_every == 0 or run["games"] >= a.games:
      run["saved"] = time.strftime("%Y-%m-%d %H:%M:%S")
      save(a.out, data)
      print(f"{run['games']} games, {run['seconds']}s; played {run['played']}", flush=True)
  print("done", flush=True)
  return 0


if __name__ == "__main__":
  sys.exit(main())
