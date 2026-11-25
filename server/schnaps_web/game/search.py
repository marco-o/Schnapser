"""A fair search player for the card play: sample the hidden hands, solve each.

Adapted for schnaps-web from open_spiel/python/scale/envs/schnaps_search.py
(the constraints, the sampler and the decision rule, unchanged in substance),
working from a pyspiel state through game/oracle.py's card-play solver
instead of the oracle's Model, which the site does not copy.

Determinized search ("perfect-information Monte Carlo"). At each card-play
decision the player deals the cards it cannot see at random, `n_samples`
times, in ways consistent with what its seat knows, solves each deal exactly
(oracle.PlaySolver: every hand open, perfect play by all) and plays the
action with the best mean value. It never looks at another hand: it reads
only its own cards, the contract, the trump and the public plays.

What a sampled deal respects:
  * hand sizes: each seat holds 5 cards minus those it played;
  * a declared pair: a seat that declared with the Koenig (Ober) of a suit
    still holds the Ober (Koenig) if it has not played it;
  * voids: a seat that did not follow the led suit has none of it; one that
    also did not trump (in a contract with trump) has no trump;
  * must-beat: a seat that followed suit without beating the best card of
    the led suit (when no trump had been played on it) has no higher card of
    that suit; one that trumped without overtrumping has no higher trump.
What the bidding says: in a Lomt, a seat other than the declarer weighs
each sampled deal by how often the declarer's whole hand (the cards it holds
in the sample and those it has played) made a Lomt in the site's played
results (game/played_table.json, smoothed). It draws `pool` times as many
deals as it solves and keeps `n_samples` of them in proportion to that
weight (sampling-importance-resampling), so the hands people call Lomt on
count most. Everywhere else every consistent deal is equally likely (the
bids of a Normal game, the passes, are not read).

Known weaknesses of the method: it assumes it will know every hand after
this move, and that its partner does too, so it overrates plays that need
the partnership to coordinate (a Schnapser with a partner, the Normal game).

Values are game points for partnership {0, 2} without the flecks (they scale
every action alike), as the solver gives them.
"""

from __future__ import annotations

import functools
import json
import os
import random
from typing import Optional

from schnaps_web.game import oracle

N_PLAYER = oracle.N_PLAYER
N_RANK = oracle.N_RANK


#: The played-results table beside this module.
PLAYED_TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "played_table.json")


@functools.lru_cache(maxsize=None)
def lomt_rates(path: str = PLAYED_TABLE) -> dict[int, float]:
  """{plain hand class key: smoothed Lomt made rate} over every seat of the
  played table ((wins + 0.5) / (n + 1)); {} when there is no table."""
  if not os.path.exists(path):
    return {}
  with open(path) as f:
    t = json.load(f)["games"]["lomt"]
  n: dict[int, float] = {}
  w: dict[int, float] = {}
  for k, kn, kw in zip(t["keys"], t["n"], t["wins"]):
    n[k // 4] = n.get(k // 4, 0.0) + kn
    w[k // 4] = w.get(k // 4, 0.0) + kw
  return {k: (w[k] + 0.5) / (n[k] + 1.0) for k in n}


def plain_key(mask: int) -> int:
  """A hand's class key, suits sorted by their rank masks (bidding.hand_keys'
  plain key)."""
  masks = [(mask >> (s * N_RANK)) & ((1 << N_RANK) - 1) for s in range(oracle.N_SUIT)]
  k = 0
  for m in sorted(masks, reverse=True):
    k = k * 32 + m
  return k


def _suit_cards(s: int) -> set[int]:
  return {s * N_RANK + r for r in range(N_RANK)}


def card_of(action: int) -> int:
  """The card a play action puts on the table (a declaration plays its
  Koenig or Ober)."""
  if oracle.FIRST_DECLARE <= action < oracle.FIRST_TRUMP:
    idx = action - oracle.FIRST_DECLARE
    return (idx // 2) * N_RANK + (oracle.KOENIG if idx % 2 == 0 else oracle.OBER)
  return action


def public_plays(state) -> list[tuple[int, int]]:
  """The deal's card-play actions so far, as (game seat, action)."""
  return [
      (item.player, item.action)
      for item in state.full_history()
      if item.player >= 0 and item.action < oracle.FIRST_TRUMP
  ]


def constraints(
    rules: oracle.Rules, plays: list[tuple[int, int]], hand: int, seat: int
):
  """What `seat`, holding the bitmask `hand`, knows of the hidden cards.

  Returns:
    (known, allowed, need): known {card: holder} for hidden cards whose
    holder is certain, allowed {card: set of seats} for the other hidden
    cards, need [cards still to place per seat] (0 for `seat`).
  """
  cards = [card_of(a) for _, a in plays]
  seats = [p for p, _ in plays]
  mine = set(oracle.cards_of(hand))
  hidden = set(range(oracle.N_CARD)) - mine - set(cards)
  others = [p for p in range(N_PLAYER) if p != seat]
  excluded = {p: set() for p in others}
  known: dict[int, int] = {}
  trump = rules.trump
  active = rules.trump_active

  # Walk the plays trick by trick.
  for t in range(0, len(cards), N_PLAYER):
    trick = cards[t : t + N_PLAYER]
    who = seats[t : t + N_PLAYER]
    led = oracle.suit_of(trick[0])
    best_led, best_trump, trumped = oracle.rank_of(trick[0]), -1, False
    if active and led == trump:
      trumped, best_trump = True, oracle.rank_of(trick[0])
    for i in range(1, len(trick)):
      c, p = trick[i], who[i]
      s, r = oracle.suit_of(c), oracle.rank_of(c)
      if p != seat:
        ex = excluded[p]
        if s != led:
          ex |= _suit_cards(led)
          if active and s != trump:
            ex |= _suit_cards(trump)
          elif active and s == trump and r < best_trump:
            ex |= {trump * N_RANK + q for q in range(best_trump + 1, N_RANK)}
        elif not (active and trumped and led != trump) and r < best_led:
          ex |= {led * N_RANK + q for q in range(best_led + 1, N_RANK)}
      if s == led:
        best_led = max(best_led, r)
      if active and s == trump:
        trumped = True
        best_trump = max(best_trump, r)

  # Declared pairs: the other card of the pair stays with the declarer.
  for p, a in plays:
    if oracle.FIRST_DECLARE <= a < oracle.FIRST_TRUMP and p != seat:
      c = card_of(a)
      s, r = oracle.suit_of(c), oracle.rank_of(c)
      other = s * N_RANK + (oracle.OBER if r == oracle.KOENIG else oracle.KOENIG)
      if other in hidden:
        known[other] = p

  need = [0] * N_PLAYER
  n_played = [0] * N_PLAYER
  for p in seats:
    n_played[p] += 1
  for p in others:
    need[p] = oracle.HAND_SIZE - n_played[p]
  for c, p in known.items():
    need[p] -= 1
  allowed = {}
  for c in hidden - set(known):
    allowed[c] = {p for p in others if c not in excluded[p]}
  return known, allowed, need


def sample_hands(
    rules: oracle.Rules,
    plays: list[tuple[int, int]],
    hand: int,
    seat: int,
    rng: random.Random,
    tries: int = 200,
) -> Optional[tuple[int, ...]]:
  """The cards each seat still holds in one deal consistent with `seat`'s
  view (`seat` keeps `hand`), or None.

  The most constrained cards are placed first, each with a seat drawn in
  proportion to its free places. The draw is not exactly uniform over the
  consistent deals, but close for the few constraints a deal carries.
  """
  known, allowed, need0 = constraints(rules, plays, hand, seat)
  base = [0] * N_PLAYER
  base[seat] = hand
  for c, p in known.items():
    base[p] |= 1 << c
  cards = list(allowed)
  for _ in range(tries):
    rng.shuffle(cards)
    cards.sort(key=lambda c: len(allowed[c]))
    need = list(need0)
    out = list(base)
    ok = True
    for c in cards:
      seats = [p for p in allowed[c] if need[p] > 0]
      if not seats:
        ok = False
        break
      p = rng.choices(seats, weights=[need[q] for q in seats])[0]
      need[p] -= 1
      out[p] |= 1 << c
    if ok and not any(need):
      return tuple(out)
  return None


def replay(rules: oracle.Rules, held: tuple[int, ...], plays) -> tuple:
  """The play state reached by `plays` from a deal whose seats now hold
  `held` (the played cards are given back to their seats first)."""
  start = list(held)
  for p, a in plays:
    start[p] |= 1 << card_of(a)
  q = oracle.initial_play(tuple(start), rules)
  for _, a in plays:
    q, v = oracle.play_apply(rules, q, a)
    if v is not None:
      raise ValueError("the deal ended during the replay")
  return q


def tie_key(action: int, trump: int):
  """The order among equally good actions: the cheapest card, a declaration
  before the same card played plainly."""
  card = card_of(action)
  declare = 0 if action >= oracle.FIRST_DECLARE else 1
  return (oracle.rank_of(card) * 2 + (oracle.suit_of(card) == trump), declare)


class Searcher:
  """Determinized search over sampled deals (module doc).

  Attributes:
    n_samples: deals sampled per decision.
    failed_samples: draws that found no consistent deal (should stay 0).
  """

  def __init__(self, n_samples: int = 20, seed: int = 0, bid_inference: bool = True,
               pool: int = 4):
    self.n_samples = n_samples
    self.rng = random.Random(seed)
    self.failed_samples = 0
    self.bid_inference = bid_inference
    self.pool = pool

  def _deals(self, rules, plays, hand, seat) -> list[tuple[int, ...]]:
    """The sampled deals to solve (module doc): uniform, or resampled by
    the declarer's Lomt rate."""
    rates = lomt_rates() if self.bid_inference else {}
    weigh = rates and rules.contract == oracle.LOMT and seat != rules.declarer
    draws = self.n_samples * (self.pool if weigh else 1)
    deals = []
    for _ in range(draws):
      held = sample_hands(rules, plays, hand, seat, self.rng)
      if held is None:
        self.failed_samples += 1
      else:
        deals.append(held)
    if not weigh or not deals:
      return deals
    d = rules.declarer
    played = 0
    for p, a in plays:
      if p == d:
        played |= 1 << card_of(a)
    weights = [rates.get(plain_key(h[d] | played), 0.0) for h in deals]
    if sum(weights) <= 0:
      return deals[: self.n_samples]
    return self.rng.choices(deals, weights=weights, k=self.n_samples)

  def action_values(self, state, seat: int) -> dict[int, float]:
    """Each legal action's mean value for partnership {0, 2} over the
    sampled deals. `state` is a pyspiel state in the card play, `seat` (a
    game seat) to move."""
    pos = oracle.position(state)  # only its rules (public) are used
    rules = pos.rules
    plays = public_plays(state)
    hand = pos.play[0][seat]
    legal = oracle.play_legal(rules, pos.play)
    total = {a: 0.0 for a in legal}
    n = 0
    solved: dict[tuple[int, ...], dict[int, float]] = {}
    for held in self._deals(rules, plays, hand, seat):
      if held not in solved:  # a resampled deal can come back
        solved[held] = oracle.PlaySolver(rules).action_values(replay(rules, held, plays))
      vals = solved[held]
      for a in legal:
        total[a] += vals[a]
      n += 1
    if n == 0:  # cannot happen with a consistent view; keep playing
      return {a: 0.0 for a in legal}
    return {a: v / n for a, v in total.items()}

  def decide(self, state, seat: int) -> int:
    """The best action for game seat `seat` (to move in the card play)."""
    legal = state.legal_actions()
    if len(legal) == 1:
      return legal[0]
    vals = self.action_values(state, seat)
    sign = 1 if oracle.team_of(seat) == 0 else -1
    best = max(sign * v for v in vals.values())
    trump = oracle.position(state).rules.trump
    tied = [a for a, v in vals.items() if sign * v >= best - 1e-9]
    return min(tied, key=lambda a: tie_key(a, trump))
