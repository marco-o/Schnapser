# Copyright 2026 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Schnaps bidding from value estimates, with pluggable bid rules.

Copied for schnaps-web from open_spiel/python/scale/envs/schnaps_bidding.py.

A bid is chosen in two steps, so that the second can change without the
first:

1. **Estimates** (`estimate`). For every legal bid, what the bidder's pair
   should expect if it makes that bid and the bidding then ends (everyone
   else passes). A value function (the player's networks) judges the
   counterfactual information state at the first play: `counterfactual`
   applies the bid, then passes, to the public bidding fields of the
   bidder's own InfoState, so only the bidder's information is used.

   | bid                         | judged by                    | value        |
   |-----------------------------|------------------------------|--------------|
   | pass, no call yet           | the Normal game's value      | V            |
   | pass after a call c         | contract c's value           | V * 2^flecks |
   | fleck                       | as pass                      | 2 * pass     |
   | call Schnapser/Lomt/Bauern  | that contract, called by me  | V            |
   | call Jodler / Hermort       | (wins at once)               | +18 / +24    |

   The counterfactual is judged with its flecks cleared and the doubling
   applied afterwards: the contract networks trained without flecks.

2. **A bid rule** (`BidRule`) picks the bid from a `BidContext`: the
   InfoState, the legal mask, the estimates and the set situation
   (`SetContext`). Rules register by name (`register_rule`), so an artifact
   records `{"rule", "rule_kwargs"}` and a new rule (for example one that
   plays for the set score) needs nothing else changed.

   * "greedy": the legal bid of highest value; a call or a fleck must beat
     passing by `margin` points.
   * "pass": always pass (the Normal-only baseline).
  * "set_aware": the bid most likely to win the set (set_win_table),
    flecking only when it cannot cost the set or the bot is very sure
    (SetAwareRule).

Hard rules. `allowed_bids` removes two calls before any rule chooses: no
Schnapser over the other partnership's contract, and no Bauern without the
trump As. The players pass only the allowed bids to `estimate` and the rule.

The set situation. `set_context(info)` reads an InfoState key "set_need"
(i32[B, 2], points each partnership still needs, seats 0/2 first) when an
env provides it, else marks the context unknown. The schnaps-web site
provides it; the "set_aware" rule uses it.

Played results. The networks' estimates of a contract are uneven (the
contract networks trained on forced deals; Schnapser by the Caller's
partner, for one, is judged about half as likely as it is). `estimate`
takes a `PlayedTable` (played_table.json, written by schnaps-web's
scripts/build_played_table.py from deals the Basic bot played out): per
hand class and seat, how many deals were played and how many won. The
estimate's chance p_net of the bidder's pair winning is moved toward them:

  p = (wins + prior * p_net) / (n + prior)

so the network counts as `prior` deals (PLAYED_PRIOR = 16, the best fit of
the played results to the network's success table) and a class with many
deals follows its played rate. The bids it applies to are the bidder's own:
passing on a Normal game (the bidder's pair winning it, valued as
NORMAL_MEAN points a deal), calling Schnapser (only by the Caller or its
partner, the seats that were played), Lomt and Bauern, and passing or
flecking on the bidder's own contract. Bids against the other pair's
contract keep the network's estimate (the played hands of a declarer were
random, not the hands people call on).

Simplifications: the estimate is myopic (it ignores later calls and flecks
by the others), and the contract networks never saw overcalls or flecks in
training, so such states are outside what they learned.
"""

import functools
import json
import os
from typing import Any, Callable, Mapping, NamedTuple, Optional, Protocol, Union

import jax
import jax.numpy as jnp
import numpy as np

from open_spiel.python.jax.games import schnaps as game

NUM_ACTIONS = game.NUM_DISTINCT_ACTIONS
PASS = game.PASS_ACTION
FLECK = game.FLECK_ACTION
#: The contracts a value function judges (index = contract id).
VALUED_CONTRACTS = (game.NORMAL, game.SCHNAPSER, game.LOMT, game.BAUERN)
#: The contracts that win at once when called.
RESOLVED_CONTRACTS = (game.JODLER, game.HERMORT)


def call_action(contract: int) -> int:
  """The action that calls `contract` (Schnapser..Hermort).

  Args:
    contract: the contract id.

  Returns:
    The action id.
  """
  return game.FIRST_CALL_ACTION + contract - 1


class SetContext(NamedTuple):
  """The set situation of each row (module doc).

  Attributes:
    known: bool[B], whether a set is being played.
    our_need: i32[B], points the bidder's partnership still needs.
    their_need: i32[B], points the other partnership still needs.
  """

  known: jax.Array
  our_need: jax.Array
  their_need: jax.Array


class BidEstimates(NamedTuple):
  """What each bid is worth (module doc), per action id; bids only.

  Attributes:
    value: f32[B, 39], expected points for the bidder's pair if it makes this
      bid and the bidding then ends; -inf on actions that are not legal bids.
    stake: f32[B, 39], points won or lost on the resulting called contract
      (points * 2^flecks); 0 for a Normal game.
    p_success: f32[B, 39], the chance the declarer's pair makes the resulting
      contract (from value and stake); NaN for a Normal game.
    my_side_declares: bool[B, 39], whether the bidder's pair is the
      declarer's.
  """

  value: jax.Array
  stake: jax.Array
  p_success: jax.Array
  my_side_declares: jax.Array


class BidContext(NamedTuple):
  """Everything a bid rule sees.

  Attributes:
    info: the bidder's InfoState, leaves [B, ...].
    legal: bool[B, 39].
    estimates: the BidEstimates.
    set: the SetContext.
  """

  info: Mapping[str, jax.Array]
  legal: jax.Array
  estimates: BidEstimates
  set: SetContext


class BidRule(Protocol):
  """Chooses a bid from a BidContext (module doc).

  Attributes:
    name: the registered name.
  """

  name: str

  def choose(self, ctx: BidContext, key: jax.Array) -> jax.Array:
    """i32[B], the chosen bid of each row (a legal bid on bidding rows)."""
    ...

  def kwargs(self) -> dict[str, Any]:
    """The JSON-able kwargs that rebuild the rule."""
    ...


_RULES: dict[str, Callable[..., BidRule]] = {}


def register_rule(name: str, ctor: Callable[..., BidRule]) -> None:
  """Registers a bid rule constructor under `name`.

  Args:
    name: the rule name.
    ctor: ctor(**kwargs) -> BidRule.

  Raises:
    ValueError: the name is taken.
  """
  if name in _RULES:
    raise ValueError(f"bid rule {name!r} is already registered")
  _RULES[name] = ctor


def make_rule(name: str, kwargs: Mapping[str, Any] | None = None) -> BidRule:
  """The bid rule `name` built with `kwargs`.

  Args:
    name: a registered rule name.
    kwargs: its kwargs.

  Returns:
    The rule.

  Raises:
    KeyError: unknown rule.
    ValueError: the rule reports another name.
  """
  if name not in _RULES:
    raise KeyError(f"unknown bid rule {name!r}; registered: {sorted(_RULES)}")
  rule = _RULES[name](**dict(kwargs or {}))
  if rule.name != name:
    raise ValueError(f"bid rule {name!r} built a rule named {rule.name!r}")
  return rule


def registered_rules() -> list[str]:
  """The registered rule names."""
  return sorted(_RULES)


def _bid_mask(legal: jax.Array) -> jax.Array:
  """The legal bids: legal actions among pass, fleck and the calls."""
  acts = jnp.arange(NUM_ACTIONS)
  return legal & (acts >= PASS)


def allowed_bids(info: Mapping[str, jax.Array], legal: jax.Array) -> jax.Array:
  """`legal` without the bids the hard rules forbid (module doc).

  Every bid rule chooses among these, whatever the estimates say:

  * no Schnapser over the other partnership's contract (the Normal game
    counts as the Caller's, seat 0): a fleck has the same best gain (6), and
    one trick taken by the other side does not lose it all;
  * no Bauern without the trump As: the As wins any trick it is played to,
    so whoever else holds it takes a trick and the Bauern fails.

  Args:
    info: the InfoStates, leaves [B, ...].
    legal: bool[B, 39].

  Returns:
    bool[B, 39].
  """
  seat = jnp.asarray(info["seat"], jnp.int32)
  theirs = jnp.asarray(info["declarer"], jnp.int32) % 2 != seat % 2
  trump = jnp.asarray(info["trump"], jnp.int32)
  hand = jnp.asarray(info["hand"], jnp.bool_)
  rows = jnp.arange(seat.shape[0])
  trump_as = jnp.clip(trump, 0, game.NUM_SUITS - 1) * game.NUM_RANKS + (
      game.NUM_RANKS - 1
  )
  has_as = (trump >= 0) & hand[rows, trump_as]
  acts = jnp.arange(NUM_ACTIONS)
  forbidden = (
      (acts == call_action(game.SCHNAPSER)) & theirs[:, None]
  ) | ((acts == call_action(game.BAUERN)) & ~has_as[:, None])
  return legal & ~forbidden


class GreedyRule:
  """The legal bid of highest value; calls and flecks must beat pass by margin.

  Attributes:
    name: "greedy".
    margin: points a call or fleck must add over passing.
  """

  name = "greedy"

  def __init__(self, margin: float = 0.0):
    self.margin = float(margin)

  def kwargs(self) -> dict[str, Any]:
    return {"margin": self.margin}

  def choose(self, ctx: BidContext, key: jax.Array) -> jax.Array:
    del key
    acts = jnp.arange(NUM_ACTIONS)
    score = ctx.estimates.value - jnp.where(acts > PASS, self.margin, 0.0)
    score = jnp.where(_bid_mask(ctx.legal), score, -jnp.inf)
    # Ties go to the lowest action id: pass first.
    return jnp.argmax(score, axis=-1).astype(jnp.int32)


class PassRule:
  """Always pass.

  Attributes:
    name: "pass".
  """

  name = "pass"

  def kwargs(self) -> dict[str, Any]:
    return {}

  def choose(self, ctx: BidContext, key: jax.Array) -> jax.Array:
    del key
    return jnp.full(ctx.legal.shape[:1], PASS, jnp.int32)


#: Points a pair needs to win a set (31 counted down).
SET_POINTS = 31
#: How many deals scored k points for the pair that won them, k: count. From
#: 2,048 deals of the site players, Large vs Basic (1,024 deal pairs, seed 1,
#: schnaps(max_flecks=2), no set score; schnaps_training/deal_points.py).
#: Used by `set_win_table`.
DEAL_POINTS = {
    1: 510, 2: 372, 3: 535, 4: 28, 6: 237, 8: 4, 9: 323, 12: 29, 18: 4,
    48: 2, 72: 4,
}


def _normal_shares(deal_points):
  """The Normal game's share of 1, 2 and 3 points (the deals worth <= 3)."""
  ks = [k for k in sorted(deal_points) if k <= 3]
  total = sum(deal_points[k] for k in ks)
  return tuple(ks), tuple(deal_points[k] / total for k in ks)


#: The points of a Normal game won, on average (DEAL_POINTS's 1, 2 and 3).
NORMAL_MEAN = float(
    sum(k * m for k, m in zip(*_normal_shares(DEAL_POINTS)))
)


def set_win_table(deal_points=None, set_points: int = SET_POINTS) -> np.ndarray:
  """W[a, b]: the chance a pair needing a points wins the set first.

  The other pair needs b. Each later deal is won by either pair with equal
  chance and is worth k points with the frequency of `deal_points`.
  W[0, b] = 1 and W[a, 0] = 0 for a, b > 0 (the set is already decided);
  W[0, 0] = 0.5 is never used.

  Args:
    deal_points: {k: count}; default DEAL_POINTS.
    set_points: the set's length.

  Returns:
    f64[set_points + 1, set_points + 1].
  """
  deal_points = DEAL_POINTS if deal_points is None else deal_points
  ks = np.asarray(sorted(deal_points), np.int64)
  ps = np.asarray([deal_points[k] for k in ks], np.float64)
  ps = ps / ps.sum()
  n = set_points
  w = np.zeros((n + 1, n + 1))
  w[0, 1:] = 1.0
  w[0, 0] = 0.5
  for total in range(2, 2 * n + 1):  # every outcome lowers a + b
    for a in range(max(1, total - n), min(n, total - 1) + 1):
      b = total - a
      won = w[np.maximum(a - ks, 0), b]
      lost = w[a, np.maximum(b - ks, 0)]
      w[a, b] = float(np.sum(ps * 0.5 * (won + lost)))
  return w


class SetAwareRule:
  """Plays for the set: each bid is valued by the chance of winning the set.

  With the set situation known, a bid's outcomes are valued by the chance
  that our pair then wins the set (`set_win_table`, value="win"):
    * a contract with stake s that our side wins with chance q:
      q * W[our - s, their] + (1 - q) * W[our, their - s];
    * a Normal game with expected value V (times 2^flecks): won or lost with
      the chance that gives V, by 1, 2 or 3 points in the shares of
      DEAL_POINTS.
  So a contract lost when the other pair needs few points counts as the set
  lost, and a long shot is called only when it really is the best chance.
  value="points" keeps the rule of 2026-11-14: a contract won is worth
  min(stake, our_need), one lost costs min(stake, their_need), and a Normal
  game's value is clipped to [-their_need, our_need]. Without the set
  situation, the plain estimates are used.

  A fleck (on the other side's contract, or back on ours) is allowed only
  when
    * it cannot cost the set: the side we bet against needs no more points
      than the contract is already worth, so it wins the set either way; or
    * our side is at least `fleck_sure` likely to win the contract.
  A fleck on the Normal game needs an expected `normal_fleck_min` points.
  The estimates of a contract seen from the defence are less reliable (the
  contract networks never saw the hands people actually call), hence the
  caution. When values are points, calls must beat passing by `margin`
  points; ties go to pass.

  Attributes:
    name: "set_aware".
  """

  name = "set_aware"

  def __init__(
      self,
      fleck_sure: float = 0.75,
      normal_fleck_min: float = 1.5,
      margin: float = 0.0,
      value: str = "win",
  ):
    if value not in ("win", "points"):
      raise ValueError(
          f"set_aware value must be 'win' or 'points', got {value!r}"
      )
    self.fleck_sure = float(fleck_sure)
    self.normal_fleck_min = float(normal_fleck_min)
    self.margin = float(margin)
    self.value = value
    self._table = set_win_table()
    self._normal = _normal_shares(DEAL_POINTS)

  def kwargs(self) -> dict[str, Any]:
    return {
        "fleck_sure": self.fleck_sure,
        "normal_fleck_min": self.normal_fleck_min,
        "margin": self.margin,
        "value": self.value,
    }

  def win_value(self, ctx: BidContext) -> jax.Array:
    """f32[B, 39]: our pair's chance of winning the set after each bid."""
    est, s = ctx.estimates, ctx.set
    q = jnp.where(est.my_side_declares, est.p_success, 1.0 - est.p_success)
    table = jnp.asarray(self._table, jnp.float32)
    n = table.shape[0] - 1
    our = s.our_need.astype(jnp.int32)[:, None]
    their = s.their_need.astype(jnp.int32)[:, None]

    def w(our_after, their_after):
      return table[jnp.clip(our_after, 0, n), jnp.clip(their_after, 0, n)]

    stake = jnp.rint(jnp.nan_to_num(est.stake)).astype(jnp.int32)
    contract = q * w(our - stake, their) + (1.0 - q) * w(our, their - stake)
    # The Normal game: its doubling per fleck, and the chance p of winning
    # it that gives the estimate V with the shares of 1, 2 and 3 points.
    acts = jnp.arange(NUM_ACTIONS)
    flecks = jnp.asarray(ctx.info["flecks"], jnp.int32)[:, None]
    mult = jnp.left_shift(1, flecks + (acts == FLECK)).astype(jnp.int32)
    ks, shares = self._normal
    mean = sum(k * m for k, m in zip(ks, shares))
    v = jnp.nan_to_num(est.value, neginf=0.0, posinf=0.0) / mult
    p = jnp.clip((v / mean + 1.0) / 2.0, 0.0, 1.0)
    normal = sum(
        m * (p * w(our - k * mult, their) + (1.0 - p) * w(our, their - k * mult))
        for k, m in zip(ks, shares)
    )
    return jnp.where(est.stake > 0, contract, normal)

  def choose(self, ctx: BidContext, key: jax.Array) -> jax.Array:
    del key
    est, s = ctx.estimates, ctx.set
    acts = jnp.arange(NUM_ACTIONS)
    our = s.our_need.astype(jnp.float32)[:, None]
    their = s.their_need.astype(jnp.float32)[:, None]
    stake = est.stake
    # Our side's chance of winning each bid's contract.
    q = jnp.where(est.my_side_declares, est.p_success, 1.0 - est.p_success)
    if self.value == "win":
      set_value = self.win_value(ctx)
    else:
      contract_value = q * jnp.minimum(stake, our) - (1.0 - q) * jnp.minimum(
          stake, their
      )
      normal_value = jnp.clip(est.value, -their, our)
      set_value = jnp.where(stake > 0, contract_value, normal_value)
    value = jnp.where(s.known[:, None], set_value, est.value)
    in_points = ~s.known | (self.value == "points")
    # The fleck's conditions, on the contract standing now (the pass entry).
    stake_now = stake[:, PASS]
    q_now = q[:, PASS]
    called = stake_now > 0
    set_free = s.known & called & (s.their_need <= stake_now)
    sure = called & (q_now >= self.fleck_sure)
    normal_ok = ~called & (est.value[:, PASS] >= self.normal_fleck_min)
    fleck_ok = set_free | sure | normal_ok
    allowed = _bid_mask(ctx.legal) & ((acts != FLECK) | fleck_ok[:, None])
    margin = jnp.where(in_points[:, None] & (acts > FLECK), self.margin, 0.0)
    score = jnp.where(allowed, value - margin, -jnp.inf)
    return jnp.argmax(score, axis=-1).astype(jnp.int32)


register_rule("greedy", GreedyRule)
register_rule("pass", PassRule)
register_rule("set_aware", SetAwareRule)


def set_context(info: Mapping[str, jax.Array]) -> SetContext:
  """The rows' set situation (module doc).

  Args:
    info: the InfoState, leaves [B, ...].

  Returns:
    The SetContext; unknown (all zeros) unless info has "set_need".
  """
  seat = jnp.asarray(info["seat"], jnp.int32)
  if "set_need" in info:
    need = jnp.asarray(info["set_need"], jnp.int32)
    us = seat % 2
    rows = jnp.arange(seat.shape[0])
    return SetContext(
        known=jnp.ones(seat.shape, jnp.bool_),
        our_need=need[rows, us],
        their_need=need[rows, 1 - us],
    )
  zeros = jnp.zeros(seat.shape, jnp.int32)
  return SetContext(
      known=jnp.zeros(seat.shape, jnp.bool_), our_need=zeros, their_need=zeros
  )


def apply_bid(info: Mapping[str, jax.Array], a) -> dict[str, jax.Array]:
  """One seat's InfoState after the next bid `a` (unbatched).

  Mirrors jax.games.schnaps.Schnaps._bid_step on the public bidding fields
  (the bidder is seat n_bids % 4). When the bid ends the bidding, the phase
  becomes play, or over for Jodler and Hermort (whose scores are not
  filled in).

  Args:
    info: one seat's InfoState, in the bidding phase.
    a: the bid (32..38).

  Returns:
    The InfoState after the bid.
  """
  a = jnp.asarray(a, jnp.int32)
  i32 = lambda k: jnp.asarray(info[k], jnp.int32)
  n_bids = i32("n_bids")
  p = n_bids % game.NUM_PLAYERS
  bidding = i32("phase") == game.PHASE_BIDDING
  is_pass = a == PASS
  is_fleck = a == FLECK
  is_call = (a >= game.FIRST_CALL_ACTION) & (a < NUM_ACTIONS)
  passes = jnp.where(is_pass, i32("passes") + 1, 0)
  contract = jnp.where(is_call, a - game.FIRST_CALL_ACTION + 1, i32("contract"))
  declarer = jnp.where(is_call, p, i32("declarer"))
  any_call = jnp.asarray(info["any_call"], jnp.bool_) | is_fleck | is_call
  flecks = jnp.where(
      is_fleck, i32("flecks") + 1, jnp.where(is_call, 0, i32("flecks"))
  )
  last_actor = jnp.where(is_fleck | is_call, p, i32("last_actor"))
  bids = jnp.asarray(info["bids"])
  bids = bids.at[n_bids].set((a - PASS).astype(bids.dtype), mode="drop")
  end = passes >= jnp.where(any_call, 3, 4)
  resolved = (contract == game.JODLER) | (contract == game.HERMORT)
  phase = jnp.where(
      end,
      jnp.where(resolved, game.PHASE_OVER, game.PHASE_PLAY),
      game.PHASE_BIDDING,
  )

  def put(k, v):
    return jnp.where(bidding, jnp.asarray(v, info[k].dtype), info[k])

  out = dict(info)
  out.update(
      phase=put("phase", phase),
      contract=put("contract", contract),
      declarer=put("declarer", declarer),
      flecks=put("flecks", flecks),
      passes=put("passes", passes),
      any_call=put("any_call", any_call),
      last_actor=put("last_actor", last_actor),
      bids=jnp.where(bidding, bids, info["bids"]),
      n_bids=put("n_bids", n_bids + 1),
  )
  return out


def counterfactual(info: Mapping[str, jax.Array], a) -> dict[str, jax.Array]:
  """One seat's InfoState after bid `a` and then passes to the end (unbatched).

  Args:
    info: one seat's InfoState, in the bidding phase.
    a: the bid.

  Returns:
    The InfoState when the bidding has ended (play, or over).
  """
  out = apply_bid(info, a)
  for _ in range(game.NUM_PLAYERS):  # at most 3 more passes are needed
    out = apply_bid(out, PASS)  # a no-op once the bidding has ended
  return out


#: value_fn(info_after, contract) -> f32[B]: the expected points of the
#: viewer's pair at the first play of `info_after`, read by the value
#: function of `contract` (a Python int for every row, or i32[B]).
ValueFn = Callable[[Mapping[str, jax.Array], Union[int, jax.Array]], jax.Array]


def _clear_flecks(info):
  out = dict(info)
  out["flecks"] = jnp.zeros_like(info["flecks"])
  return out


#: Deals the network's estimate counts for against played results (module
#: doc, "Played results").
PLAYED_PRIOR = 16.0
#: The played-results table beside this module.
PLAYED_TABLE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "played_table.json"
)
PLAYED_SCHEMA = "schnaps-played-table/1"
PLAYED_GAMES = (
    "normal", "schnapser_caller", "schnapser_partner", "lomt", "bauern"
)


class PlayedTable:
  """Played deals and wins per hand class and seat (module doc).

  A game's entries are keyed by (((m0 * 32 + m1) * 32 + m2) * 32 + m3) * 4 +
  seat, m0..m3 the hand's class key (`hand_keys`).

  Attributes:
    games: {game: (keys i32[N] ascending, n f32[N], wins f32[N])}.
    source: the table's "source" record.
  """

  def __init__(self, games: Mapping[str, Mapping[str, Any]], source=None):
    self.games = {}
    for g in PLAYED_GAMES:
      e = games.get(g) or {"keys": [], "n": [], "wins": []}
      keys = np.asarray(e["keys"], np.int32)
      order = np.argsort(keys, kind="stable")
      self.games[g] = (
          keys[order],
          np.asarray(e["n"], np.float32)[order],
          np.asarray(e["wins"], np.float32)[order],
      )
    self.source = dict(source or {})

  def lookup(self, name: str, key: jax.Array) -> tuple[jax.Array, jax.Array]:
    """(n, wins) f32[B] of game `name` at the keys i32[B]; 0 where unseen."""
    keys, n, wins = self.games[name]
    zeros = jnp.zeros(jnp.shape(key), jnp.float32)
    if keys.size == 0:
      return zeros, zeros
    k = jnp.asarray(keys)
    i = jnp.clip(jnp.searchsorted(k, key), 0, keys.size - 1)
    hit = k[i] == key
    return (
        jnp.where(hit, jnp.asarray(n)[i], zeros),
        jnp.where(hit, jnp.asarray(wins)[i], zeros),
    )


@functools.lru_cache(maxsize=None)
def load_played_table(path: str = PLAYED_TABLE) -> Optional[PlayedTable]:
  """The PlayedTable at `path`, or None when there is no such file.

  Args:
    path: a played_table.json.

  Returns:
    The table, or None.

  Raises:
    ValueError: the file has another schema.
  """
  if not os.path.exists(path):
    return None
  with open(path) as f:
    data = json.load(f)
  if data.get("schema") != PLAYED_SCHEMA:
    raise ValueError(
        f"{path}: schema {data.get('schema')!r} is not {PLAYED_SCHEMA}"
    )
  return PlayedTable(data["games"], data.get("source"))


def hand_keys(info: Mapping[str, jax.Array]) -> tuple[jax.Array, jax.Array]:
  """The hands' class keys as integers: (trump-marked, plain), i32[B].

  The four suit rank masks (bit r = rank r held, Unter..As) packed in base
  32: trump first and the other suits descending (marked), or all four
  descending (plain, Lomt). As schnaps-web's success.class_key.

  Args:
    info: the InfoStates, leaves [B, ...].

  Returns:
    (marked, plain).
  """
  hand = jnp.asarray(info["hand"], jnp.int32)
  b = hand.shape[0]
  masks = jnp.sum(
      hand.reshape(b, game.NUM_SUITS, game.NUM_RANKS)
      << jnp.arange(game.NUM_RANKS, dtype=jnp.int32),
      axis=-1,
  )

  def pack(ms):
    k = ms[:, 0]
    for j in range(1, game.NUM_SUITS):
      k = k * 32 + ms[:, j]
    return k

  plain = pack(-jnp.sort(-masks, axis=-1))
  trump = jnp.clip(jnp.asarray(info["trump"], jnp.int32), 0, game.NUM_SUITS - 1)
  rows = jnp.arange(b)
  others = jnp.where(
      jnp.arange(game.NUM_SUITS) == trump[:, None], -1, masks
  )
  others = -jnp.sort(-others, axis=-1)[:, : game.NUM_SUITS - 1]
  marked = pack(jnp.concatenate([masks[rows, trump][:, None], others], axis=1))
  return marked, plain


def played_results(
    table: PlayedTable, info: Mapping[str, jax.Array], contract: int
) -> tuple[jax.Array, jax.Array]:
  """(n, wins) f32[B]: the bidder's pair's played deals in `contract`.

  The Normal game: the bidder's pair winning it. A contract: the bidder
  declaring it and making it (Schnapser only from seats 0 and 2).

  Args:
    table: the PlayedTable.
    info: the bidders' InfoStates, leaves [B, ...].
    contract: NORMAL, SCHNAPSER, LOMT or BAUERN.

  Returns:
    (n, wins).
  """
  seat = jnp.asarray(info["seat"], jnp.int32)
  marked, plain = hand_keys(info)
  if contract == game.NORMAL:
    return table.lookup("normal", marked * 4 + seat)
  if contract == game.SCHNAPSER:
    nc, wc = table.lookup("schnapser_caller", marked * 4)
    np_, wp = table.lookup("schnapser_partner", marked * 4 + 2)
    zero = jnp.zeros_like(nc)
    n = jnp.where(seat == 0, nc, jnp.where(seat == 2, np_, zero))
    w = jnp.where(seat == 0, wc, jnp.where(seat == 2, wp, zero))
    return n, w
  if contract == game.LOMT:
    return table.lookup("lomt", plain * 4)
  if contract == game.BAUERN:
    return table.lookup("bauern", marked * 4 + seat)
  raise ValueError(f"no played results for contract {contract}")


def _toward_played(v, points, n, wins, prior):
  """v (the pair's points, won or lost `points`) moved to the played rate."""
  p_net = jnp.clip((v / points + 1.0) / 2.0, 0.0, 1.0)
  p = (wins + prior * p_net) / (n + prior)
  return v + 2.0 * points * (p - p_net)


def estimate(
    info: Mapping[str, jax.Array],
    legal: jax.Array,
    value_fn: ValueFn,
    played: Optional[PlayedTable] = None,
    prior: float = PLAYED_PRIOR,
) -> BidEstimates:
  """The BidEstimates of every row (module doc).

  Args:
    info: the bidders' InfoStates, leaves [B, ...].
    legal: bool[B, 39].
    value_fn: the value function (ValueFn).
    played: played results to move the bidder's own bids toward (module doc,
      "Played results"); None keeps the value function's estimates.
    prior: the deals the value function counts for (> 0).

  Returns:
    The BidEstimates.
  """
  if played is not None and not prior > 0:
    raise ValueError(f"the played-results prior must be > 0, got {prior}")
  seat = jnp.asarray(info["seat"], jnp.int32)
  b = seat.shape[0]
  points = jnp.asarray(game.CONTRACT_POINTS, jnp.float32)
  cf = jax.vmap(counterfactual)
  if played is not None:
    results = {c: played_results(played, info, c) for c in VALUED_CONTRACTS}

  value = jnp.full((b, NUM_ACTIONS), -jnp.inf, jnp.float32)
  stake = jnp.zeros((b, NUM_ACTIONS), jnp.float32)
  mine = jnp.zeros((b, NUM_ACTIONS), jnp.bool_)

  # Pass (and fleck): the contract standing now.
  after = cf(info, jnp.full((b,), PASS, jnp.int32))
  contract = jnp.clip(jnp.asarray(after["contract"], jnp.int32), 0, 3)
  mult = 2.0 ** jnp.asarray(after["flecks"], jnp.float32)
  v_pass = value_fn(_clear_flecks(after), contract) * mult
  called = contract != game.NORMAL
  s_pass = jnp.where(called, points[contract] * mult, 0.0)
  declarer = jnp.asarray(after["declarer"], jnp.int32)
  m_pass = declarer % 2 == seat % 2
  if played is not None:
    # A Normal game, or the bidder's own contract.
    n = jnp.zeros((b,), jnp.float32)
    w = jnp.zeros((b,), jnp.float32)
    for c in VALUED_CONTRACTS:
      sel = (contract == c) & ((c == game.NORMAL) | (declarer == seat))
      n = jnp.where(sel, results[c][0], n)
      w = jnp.where(sel, results[c][1], w)
    v_pass = _toward_played(
        v_pass, jnp.where(called, s_pass, NORMAL_MEAN * mult), n, w, prior
    )
  value = value.at[:, PASS].set(v_pass)
  stake = stake.at[:, PASS].set(s_pass)
  mine = mine.at[:, PASS].set(m_pass)
  value = value.at[:, FLECK].set(2.0 * v_pass)
  stake = stake.at[:, FLECK].set(2.0 * s_pass)
  mine = mine.at[:, FLECK].set(m_pass)

  # Calls judged by their contract's value function.
  for c in VALUED_CONTRACTS[1:]:
    a = call_action(c)
    after_c = cf(info, jnp.full((b,), a, jnp.int32))
    v_c = value_fn(after_c, c)
    if played is not None:
      v_c = _toward_played(v_c, points[c], *results[c], prior)
    value = value.at[:, a].set(v_c)
    stake = stake.at[:, a].set(points[c])
    mine = mine.at[:, a].set(True)
  # Calls that win at once.
  for c in RESOLVED_CONTRACTS:
    a = call_action(c)
    value = value.at[:, a].set(points[c])
    stake = stake.at[:, a].set(points[c])
    mine = mine.at[:, a].set(True)

  bids = _bid_mask(legal)
  value = jnp.where(bids, value, -jnp.inf)
  declarer_value = jnp.where(mine, value, -value)
  p = jnp.clip((declarer_value / jnp.maximum(stake, 1e-9) + 1.0) / 2.0, 0, 1)
  p = jnp.where(bids & (stake > 0), p, jnp.nan)
  return BidEstimates(
      value=value, stake=stake, p_success=p, my_side_declares=mine & bids
  )
