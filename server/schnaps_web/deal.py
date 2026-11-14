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
   "returns": [game seats' returns] or None}

A seated viewer sees its own hand only, and its legal moves when it is to
move; a spectator (None) sees no hand and no moves.
"""

import random
from typing import Optional

import pyspiel

from schnaps_web import match
from schnaps_web.game import view

GAME_STRING = "schnaps(max_flecks=2)"


class DealError(ValueError):
  """A move the deal refuses (not that seat's turn, not legal, finished)."""


class Deal:
  """One deal (module doc).

  Attributes:
    dealer: the dealer's table seat.
    state: the pyspiel state, never at a chance node between moves.
  """

  def __init__(self, game: pyspiel.Game, dealer: int, rng: random.Random):
    self.dealer = dealer
    self._rng = rng
    self.state = game.new_initial_state()
    self._deal_chance()

  def _deal_chance(self) -> None:
    while self.state.is_chance_node():
      actions, probs = zip(*self.state.chance_outcomes())
      self.state.apply_action(self._rng.choices(actions, probs)[0])

  @property
  def is_over(self) -> bool:
    return self.state.is_terminal()

  def game_seat(self, seat: int) -> int:
    return match.game_seat(seat, self.dealer)

  def table_seat(self, game_seat: int) -> int:
    return match.table_seat(game_seat, self.dealer)

  def to_move(self) -> Optional[int]:
    """The table seat to move, None when the deal is over."""
    if self.state.is_terminal():
      return None
    return self.table_seat(self.state.current_player())

  def apply(self, seat: int, action: int) -> str:
    """Plays `seat`'s move.

    Args:
      seat: the table seat.
      action: the action id.

    Returns:
      The move as the log names it, e.g. "Call Lomt".

    Raises:
      DealError: the deal is over, it is not `seat`'s turn, or the action is
        not legal.
    """
    if self.state.is_terminal():
      raise DealError("the deal is over")
    if self.to_move() != seat:
      raise DealError(f"it is not seat {seat}'s turn")
    if action not in self.state.legal_actions():
      raise DealError(f"action {action} is not legal")
    text = view.action_text(self.state, action)
    self.state.apply_action(action)
    self._deal_chance()
    return text

  def frame(self, seat: Optional[int]) -> dict:
    """What table seat `seat` (None: a spectator) may see (module doc)."""
    viewer = None if seat is None else self.game_seat(seat)
    actions = []
    if viewer is not None and not self.state.is_terminal():
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
            "view": view.present(self.state, viewer),
            "actions": actions,
        },
        "returns": (
            [float(r) for r in self.state.returns()]
            if self.state.is_terminal()
            else None
        ),
    }

  def result(self) -> dict:
    """The finished deal's returns and contract, for match.Match.record.

    Returns:
      {"returns", "contract", "declarer" (game seat or None), "flecks"}.

    Raises:
      DealError: the deal is not over.
    """
    if not self.state.is_terminal():
      raise DealError("the deal is not over")
    contract = view.contract_of(self.state)
    name, declarer, flecks = contract if contract else ("Normal", None, 0)
    return {
        "returns": [float(r) for r in self.state.returns()],
        "contract": name,
        "declarer": None if name == "Normal" else declarer,
        "flecks": flecks,
    }
