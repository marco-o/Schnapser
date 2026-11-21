"""One schnaps deal on the pyspiel engine, seen from the table's seats.

The engine numbers seats from the Caller (game seat 0); the table numbers
them round the table. A Deal knows its dealer and translates (match.py):
moves and frames take table seats.

A frame is what one viewer may see, the JSON the client's table renderer
reads:

  {"viewer": {"seat": game seat or None},
   "seatMap": [table seat of game seat 0..3],
   "presentation": {"view": game.view.present(...),
                    "actions": [{"id", "label", "hint"}]},  # the viewer's moves
   "throws": {"resign": bool, "show": bool},  # offered to the viewer
   "returns": [game seats' returns] or None}

A seated viewer sees its own hand only, and its legal moves when it is to
move; a spectator (None) sees no hand and no moves.

cardthrowup (docs/cardthrowup.md), during the card play:

  * Show: a seat lays its hand open to the two opponents (not its partner,
    not spectators), so they can see the deal is lost and resign. Play goes
    on; the hand stays open to them for the rest of the deal, as it is
    played down. Offered during the whole play, once per seat.
  * Resign: ends the deal at once and is always accepted. The resigner's
    side loses: a contract fails (declaring side) or is made (defenders);
    in a Normal game the other side wins as if it had just reached 66 (3
    if the resigners have no trick, 2 if under 33 points, else 1). All
    times 2^flecks. Offered during the whole play of a contract; in a
    Normal game from the third trick, or at once when an opponent has shown
    their hand.

A resigned deal keeps its state as it was at the throw; every hand then
shows to everyone, and its returns come from the throw. The view carries
the throw and the shown seats (game.view.present).
"""

import dataclasses
import random
from typing import Optional

import pyspiel

from schnaps_web import match
from schnaps_web.game import oracle
from schnaps_web.game import view

GAME_STRING = "schnaps(max_flecks=2)"

#: Tricks finished before a Normal game's side may resign (the third trick).
NORMAL_RESIGN_FROM = 2


class DealError(ValueError):
  """A move the deal refuses (not that seat's turn, not legal, finished)."""


@dataclasses.dataclass(frozen=True)
class Throw:
  """A cardthrowup that ended the deal (module doc): a resignation.

  Attributes:
    kind: "resign".
    seat: the thrower's game seat.
    trick: the tricks finished at the throw.
    returns: the game seats' returns the throw gives.
  """

  kind: str
  seat: int
  trick: int
  returns: tuple[float, ...]

  @property
  def text(self) -> str:
    """The deal log's name: "Resign"."""
    return view.throw_text(self.kind)

  def to_json(self) -> dict:
    return {
        "kind": self.kind,
        "seat": self.seat,
        "trick": self.trick,
        "text": self.text,
    }


class Deal:
  """One deal (module doc).

  Attributes:
    dealer: the dealer's table seat.
    state: the pyspiel state, never at a chance node between moves. After a
      throw it stays as it was at the throw.
    throw: the throw that ended the deal, or None.
    shown: the game seats that showed their hand to the opponents.
  """

  def __init__(self, game: pyspiel.Game, dealer: int, rng: random.Random):
    self.dealer = dealer
    self._rng = rng
    self.state = game.new_initial_state()
    self.throw: Optional[Throw] = None
    self.shown: set[int] = set()
    self._deal_chance()

  def _deal_chance(self) -> None:
    while self.state.is_chance_node():
      actions, probs = zip(*self.state.chance_outcomes())
      self.state.apply_action(self._rng.choices(actions, probs)[0])

  @property
  def is_over(self) -> bool:
    return self.throw is not None or self.state.is_terminal()

  def game_seat(self, seat: int) -> int:
    return match.game_seat(seat, self.dealer)

  def table_seat(self, game_seat: int) -> int:
    return match.table_seat(game_seat, self.dealer)

  def to_move(self) -> Optional[int]:
    """The table seat to move, None when the deal is over."""
    if self.is_over:
      return None
    return self.table_seat(self.state.current_player())

  def apply(self, seat: int, action: int) -> str:
    """Plays `seat`'s move.

    Args:
      seat: the table seat.
      action: the action id.

    Returns:
      The move as the log names it, e.g. "Lomt".

    Raises:
      DealError: the deal is over, it is not `seat`'s turn, or the action is
        not legal.
    """
    if self.is_over:
      raise DealError("the deal is over")
    if self.to_move() != seat:
      raise DealError(f"it is not seat {seat}'s turn")
    if action not in self.state.legal_actions():
      raise DealError(f"action {action} is not legal")
    text = view.action_text(self.state, action)
    self.state.apply_action(action)
    self._deal_chance()
    return text

  def frame(self, seat: Optional[int], reveal: bool = False) -> dict:
    """What table seat `seat` (None: a spectator) may see (module doc).

    `reveal` shows every hand (the all-cards watch port, spectators only).
    """
    viewer = None if seat is None else self.game_seat(seat)
    actions = []
    if viewer is not None and not self.is_over:
      if self.state.current_player() == viewer:
        legal = self.state.legal_actions()
        hints = view.describe_actions(self.state, legal)
        actions = [
            {
                "id": int(a),
                "label": view.action_text(self.state, a),
                "hint": hints.get(a),
            }
            for a in legal
        ]
    return {
        "viewer": {"seat": viewer},
        "seatMap": [self.table_seat(g) for g in range(match.NUM_SEATS)],
        "presentation": {
            "view": view.present(
                self.state,
                viewer,
                reveal,
                self.throw.to_json() if self.throw else None,
                sorted(self.shown),
            ),
            "actions": actions,
        },
        "throws": {
            "resign": seat is not None and self.can_resign(seat),
            "show": seat is not None and self.can_show(seat),
        },
        "returns": self._returns() if self.is_over else None,
    }

  def _returns(self) -> list[float]:
    if self.throw is not None:
      return list(self.throw.returns)
    return [float(r) for r in self.state.returns()]

  def result(self) -> dict:
    """The finished deal's returns and contract, for match.Match.record.

    Returns:
      {"returns", "contract", "declarer" (game seat or None), "flecks",
      "throw" (Throw.to_json, or None)}.

    Raises:
      DealError: the deal is not over.
    """
    if not self.is_over:
      raise DealError("the deal is not over")
    contract = view.contract_of(self.state)
    name, declarer, flecks = contract if contract else ("Normal", None, 0)
    return {
        "returns": self._returns(),
        "contract": name,
        "declarer": None if name == "Normal" else declarer,
        "flecks": flecks,
        "throw": self.throw.to_json() if self.throw else None,
    }

  # -- cardthrowup -----------------------------------------------------------

  def in_play(self) -> bool:
    """Whether the deal is in its card play (and not over)."""
    if self.is_over:
      return False
    return any(
        line.rstrip() == "Phase: Play" for line in str(self.state).splitlines()
    )

  def can_show(self, seat: int) -> bool:
    """Whether table seat `seat` is offered Show: the card play, once."""
    return self.in_play() and self.game_seat(seat) not in self.shown

  def show(self, seat: int) -> None:
    """Table seat `seat` lays its hand open to the opponents (module doc).

    Raises:
      DealError: not in the card play, or already shown.
    """
    if not self.in_play():
      raise DealError("you can only show your cards during the card play")
    if self.game_seat(seat) in self.shown:
      raise DealError("your cards are already shown")
    self.shown.add(self.game_seat(seat))

  def can_resign(self, seat: int) -> bool:
    """Whether table seat `seat` is offered Resign (module doc)."""
    if not self.in_play():
      return False
    pos = oracle.position(self.state)
    if pos.rules.contract != oracle.NORMAL:
      return True
    team = oracle.team_of(self.game_seat(seat))
    opponent_shown = any(oracle.team_of(g) != team for g in self.shown)
    return opponent_shown or pos.play[6] >= NORMAL_RESIGN_FROM

  def resign(self, seat: int) -> str:
    """Table seat `seat` resigns for its side; returns the log text.

    Raises:
      DealError: Resign is not offered now (module doc).
    """
    if not self.can_resign(seat):
      raise DealError("you cannot resign now")
    g = self.game_seat(seat)
    pos = oracle.position(self.state)
    self.throw = Throw("resign", g, pos.play[6], _resign_returns(pos, g))
    return self.throw.text


def _resign_returns(pos: oracle.Position, g: int) -> tuple[float, ...]:
  """The game seats' returns when game seat `g`'s side gives up now."""
  rules, p = pos.rules, pos.play
  team = oracle.team_of(g)
  if rules.contract == oracle.NORMAL:
    winner = 1 - team
    # As if the winners had just reached 66.
    base = abs(oracle.finish_normal(winner, p[3], p[4]))
  else:
    base = oracle.CONTRACT_POINTS[rules.contract]
    declaring = oracle.team_of(rules.declarer)
    winner = 1 - declaring if team == declaring else declaring
  v = float(base * 2**pos.flecks)
  return tuple(
      v if oracle.team_of(s) == winner else -v for s in range(match.NUM_SEATS)
  )
