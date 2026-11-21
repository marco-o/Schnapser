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

"""The card play with every hand open: rules, an exact solver, positions.

Copied for schnaps-web from open_spiel/python/scale/envs/schnaps_oracle.py
(the card-play part: Rules, initial_play, play_legal, play_apply and
PlaySolver, unchanged). The oracle's Model, bidding and Oracle are left out.
schnaps-web adds:

  * `finish_normal`: a Normal game's score when a side resigns now.
  * `position(state)`: a pyspiel play state as the solver's play tuple
    (replayed from the history, checked against the state's text).

Values are in game points for partnership {0, 2} (seats 0 and 2), + when it
wins, without the flecks (the caller doubles them). Seats are game seats.
"""

from __future__ import annotations

import dataclasses
import re

N_PLAYER = 4
N_SUIT = 4
N_RANK = 5
N_CARD = 20
HAND_SIZE = 5
RANK_POINTS = (2, 3, 4, 10, 11)
CONTRACT_POINTS = (3, 6, 9, 12, 18, 24)
NORMAL, SCHNAPSER, LOMT, BAUERN, JODLER, HERMORT = range(6)
CONTRACT_NAMES = ("Normal", "Schnapser", "Lomt", "Bauern", "Jodler", "Hermort")
OBER, KOENIG = 1, 2
FIRST_DECLARE = 20
FIRST_TRUMP = 28
WINNING_POINTS = 66
INF = 10**6


def suit_of(card: int) -> int:
  return card // N_RANK


def rank_of(card: int) -> int:
  return card % N_RANK


def team_of(seat: int) -> int:
  return seat % 2


def cards_of(mask: int) -> list[int]:
  """The cards of a bitmask, ascending."""
  return [c for c in range(N_CARD) if mask >> c & 1]


# ------------------------------- Card play ---------------------------------
#
# A play state is a tuple (hands, trick, leader, score, tricks, pending, n):
#   hands    4 bitmasks of the cards each seat still holds
#   trick    the cards of the trick in progress, in order (seat leader + i)
#   leader   the seat that led it
#   score    (team 0, team 1) points: cards and valid declarations
#   tricks   (team 0, team 1) tricks won
#   pending  (team 0, team 1) declarations awaiting the team's first trick
#   n        tricks played
# The rules of a deal's play are fixed: Rules.


@dataclasses.dataclass(frozen=True)
class Rules:
  """What stays fixed during a deal's play."""

  trump: int  # the trump suit (still set in a Lomt, where it does not count)
  contract: int
  declarer: int

  @property
  def trump_active(self) -> bool:
    return self.contract != LOMT


def initial_play(hands: tuple[int, ...], rules: Rules) -> tuple:
  """The play state when the bidding ends."""
  leader = rules.declarer if rules.contract == LOMT else 0
  return (tuple(hands), (), leader, (0, 0), (0, 0), (0, 0), 0)


def to_move(p: tuple) -> int:
  return (p[2] + len(p[1])) % N_PLAYER


def play_legal(rules: Rules, p: tuple) -> list[int]:
  """The legal play actions (SchnapsState::PlayActions)."""
  hands, trick, leader = p[0], p[1], p[2]
  seat = (leader + len(trick)) % N_PLAYER
  hand = cards_of(hands[seat])
  if not trick:
    actions = list(hand)
    if rules.contract in (NORMAL, SCHNAPSER):
      for s in range(N_SUIT):
        k, o = s * N_RANK + KOENIG, s * N_RANK + OBER
        if hands[seat] >> k & 1 and hands[seat] >> o & 1:
          actions += [FIRST_DECLARE + 2 * s, FIRST_DECLARE + 2 * s + 1]
    return actions
  active = rules.trump_active
  led = suit_of(trick[0])
  best_led, best_trump, trumped = -1, -1, False
  for c in trick:
    s, r = suit_of(c), rank_of(c)
    if active and s == rules.trump:
      trumped = True
      best_trump = max(best_trump, r)
    if s == led:
      best_led = max(best_led, r)
  follow = [c for c in hand if suit_of(c) == led]
  if follow:
    if not (active and trumped and led != rules.trump):
      higher = [c for c in follow if rank_of(c) > best_led]
      if higher:
        return higher
    return follow
  if active:
    trumps = [c for c in hand if suit_of(c) == rules.trump]
    if trumps:
      higher = [c for c in trumps if rank_of(c) > best_trump]
      return higher or trumps
  return hand


def _finish_normal(winner: int, score, tricks) -> int:
  loser = 1 - winner
  if tricks[loser] == 0:
    base = 3
  elif score[loser] < 33:
    base = 2
  else:
    base = 1
  return base if winner == 0 else -base


def _contract_end(rules: Rules, winner_team: int) -> int:
  v = CONTRACT_POINTS[rules.contract]
  return v if winner_team == 0 else -v


def _check_end(rules, score, tricks, n, last_winner, after_trick):
  """The deal's value for team 0 if it ended, else None (CheckGameEnd)."""
  c = rules.contract
  if c == NORMAL:
    for t in (0, 1):
      if score[t] >= WINNING_POINTS:
        return _finish_normal(t, score, tricks)
    if after_trick and n == HAND_SIZE:
      return _finish_normal(team_of(last_winner), score, tricks)
    return None
  if c == SCHNAPSER:
    t = team_of(rules.declarer)
    if score[t] >= WINNING_POINTS:
      return _contract_end(rules, t)
    # A trick won by the other side, or the third trick, ends it.
    if after_trick and (team_of(last_winner) != t or n == 3):
      return _contract_end(rules, 1 - t)
    return None
  if c in (LOMT, BAUERN):
    if not after_trick:
      return None
    t = team_of(rules.declarer)
    if last_winner != rules.declarer:
      return _contract_end(rules, 1 - t)
    if n == HAND_SIZE:
      return _contract_end(rules, t)
    return None
  return None


def _beats(rules: Rules, a: int, b: int) -> bool:
  ta = rules.trump_active and suit_of(a) == rules.trump
  tb = rules.trump_active and suit_of(b) == rules.trump
  if ta != tb:
    return ta
  return suit_of(a) == suit_of(b) and rank_of(a) > rank_of(b)


def play_apply(rules: Rules, p: tuple, action: int):
  """Applies a play action: (the next play state, its value or None).

  The value is the deal's value for team 0 when the action ends the deal.
  """
  hands, trick, leader, score, tricks, pending, n = p
  seat = (leader + len(trick)) % N_PLAYER
  team = team_of(seat)
  if FIRST_DECLARE <= action < FIRST_TRUMP:
    idx = action - FIRST_DECLARE
    s = idx // 2
    card = s * N_RANK + (KOENIG if idx % 2 == 0 else OBER)
    pts = 40 if s == rules.trump else 20
    if tricks[team] > 0:
      score = _add(score, team, pts)
    else:
      pending = _add(pending, team, pts)
    v = _check_end(rules, score, tricks, n, -1, False)
    if v is not None:
      return (hands, trick, leader, score, tricks, pending, n), v
  else:
    card = action
  hands = tuple(h & ~(1 << card) if i == seat else h for i, h in enumerate(hands))
  trick = trick + (card,)
  if len(trick) < N_PLAYER:
    return (hands, trick, leader, score, tricks, pending, n), None
  win = 0
  pts = 0
  for i, c in enumerate(trick):
    pts += RANK_POINTS[rank_of(c)]
    if i > 0 and _beats(rules, c, trick[win]):
      win = i
  winner = (leader + win) % N_PLAYER
  wt = team_of(winner)
  score = _add(score, wt, pts + pending[wt])
  pending = _add(pending, wt, -pending[wt])
  tricks = _add(tricks, wt, 1)
  n += 1
  q = (hands, (), winner, score, tricks, pending, n)
  return q, _check_end(rules, score, tricks, n, winner, True)


def _add(pair, i, v):
  return (pair[0] + v, pair[1]) if i == 0 else (pair[0], pair[1] + v)


class PlaySolver:
  """Exact minimax of a deal's card play, full information (module doc)."""

  def __init__(self, rules: Rules):
    self.rules = rules
    self.table: dict[tuple, tuple[int, int]] = {}
    self.nodes = 0

  def value(self, p: tuple) -> int:
    """The play state's value for team 0 under perfect play by all."""
    return self._search(p, -INF, INF)

  def action_values(self, p: tuple) -> dict[int, int]:
    """Each legal action's exact value for team 0."""
    out = {}
    for a in play_legal(self.rules, p):
      q, v = play_apply(self.rules, p, a)
      out[a] = v if v is not None else self.value(q)
    return out

  def _search(self, p, alpha, beta):
    self.nodes += 1
    lo, hi = self.table.get(p, (-INF, INF))
    if lo >= beta:
      return lo
    if hi <= alpha:
      return hi
    if lo == hi:
      return lo
    alpha, beta = max(alpha, lo), min(beta, hi)
    a0, b0 = alpha, beta
    maximise = team_of(to_move(p)) == 0
    best = -INF if maximise else INF
    for a in play_legal(self.rules, p):
      q, v = play_apply(self.rules, p, a)
      if v is None:
        v = self._search(q, alpha, beta)
      if maximise:
        if v > best:
          best = v
          alpha = max(alpha, v)
      elif v < best:
        best = v
        beta = min(beta, v)
      if alpha >= beta:
        break
    if best <= a0:
      self.table[p] = (lo, min(hi, best))
    elif best >= b0:
      self.table[p] = (max(lo, best), hi)
    else:
      self.table[p] = (best, best)
    return best


# ------------------------- schnaps-web: Resign -----------------------------

#: A Normal game's value for team 0 when team `winner` ends it now (1, 2 or
#: 3, + for team 0): the scoring of a Normal-game resignation.
finish_normal = _finish_normal


def _card_of(action: int) -> int:
  if FIRST_DECLARE <= action < FIRST_TRUMP:
    s = (action - FIRST_DECLARE) // 2
    return s * N_RANK + (KOENIG if (action - FIRST_DECLARE) % 2 == 0 else OBER)
  return action


# --------------------- schnaps-web: from a pyspiel state -------------------

_GAME_RANKS = ("U", "O", "K", "Z", "A")
_GAME_SUITS = ("h", "c", "p", "k")
_CONTRACT = re.compile(r"^Contract: (\w+) by P(\d), flecks=(\d+)$")
_SCORE = re.compile(r"^Score: (\d+)-(\d+)\s+Tricks: (\d+)-(\d+)$")


def _parse_card(text: str) -> int:
  return _GAME_SUITS.index(text[1]) * N_RANK + _GAME_RANKS.index(text[0])


@dataclasses.dataclass(frozen=True)
class Position:
  """A pyspiel deal in the card play, for the solvers.

  Attributes:
    rules: the play's rules.
    flecks: the flecks on the contract (values are doubled per fleck).
    play: the play state tuple.
  """

  rules: Rules
  flecks: int
  play: tuple


def position(state) -> Position:
  """The pyspiel `state`, which must be in the card play, as a Position.

  The play is replayed from the history (the solver's rules, which the
  oracle's tests check against pyspiel move for move) and checked against
  the state's text: the hands, score and tricks must agree.

  Raises:
    ValueError: the state is not in the card play, or the replay disagrees.
  """
  text = str(state)
  phase, trump, contract = None, None, None
  hands = [[] for _ in range(N_PLAYER)]
  score = tricks = None
  for line in text.splitlines():
    line = line.rstrip()
    if line.startswith("Phase: "):
      phase = line[len("Phase: "):]
    elif line.startswith("Trump: "):
      trump = _GAME_SUITS.index(line[len("Trump: "):])
    elif re.match(r"^P\d:", line):
      hands[int(line[1])] = [_parse_card(c) for c in line[3:].split()]
    elif line.startswith("Contract: "):
      m = _CONTRACT.match(line)
      if m:
        contract = (m[1], int(m[2]), int(m[3]))
    elif line.startswith("Score: "):
      m = _SCORE.match(line)
      if m:
        score = (int(m[1]), int(m[2]))
        tricks = (int(m[3]), int(m[4]))
  if phase != "Play" or trump is None:
    raise ValueError(f"not in the card play (phase {phase!r})")
  name, declarer, flecks = contract or ("Normal", 0, 0)
  rules = Rules(trump, CONTRACT_NAMES.index(name), declarer)
  plays = [
      (item.player, item.action)
      for item in state.full_history()
      if item.player >= 0 and item.action < FIRST_TRUMP
  ]
  start = [0] * N_PLAYER
  for seat in range(N_PLAYER):
    for c in hands[seat]:
      start[seat] |= 1 << c
  for seat, a in plays:
    start[seat] |= 1 << _card_of(a)
  p = initial_play(tuple(start), rules)
  for seat, a in plays:
    if to_move(p) != seat:
      raise ValueError("the replay's turn order disagrees with the state")
    p, v = play_apply(rules, p, a)
    if v is not None:
      raise ValueError("the replay ended before the state did")
  mine = tuple(sum(1 << c for c in h) for h in hands)
  if p[0] != mine or (score is not None and (p[3], p[4]) != (score, tricks)):
    raise ValueError("the replay disagrees with the state")
  if to_move(p) != state.current_player():
    raise ValueError("the replay's player to move disagrees with the state")
  return Position(rules, flecks, p)
