"""Sets, matches, the dealer and the seat mapping (pure, no game engine).

Table seats 0..3 go clockwise; the pairs are seats 0 and 2 (pair 0) against
seats 1 and 3 (pair 1), fixed for the whole match.

The dealer moves one seat clockwise after every deal. The Caller (the
game's seat 0, who chooses trump, bids first and leads a Normal game) is the
dealer's left neighbour, the next seat clockwise. Game seat g sits at table
seat (caller + g) % 4: the game's turn order 0, 1, 2, 3 is clockwise round
the table.

A set: both pairs start at SET_POINTS (31) and count down by the points
they win; the first pair at or below 0 wins the set. A match: the first
pair to win SETS_TO_WIN (2) sets.

A deal's points are the winning side's game return: 1, 2 or 3 for a Normal
game, 6 / 9 / 12 / 18 / 24 for Schnapser, Lomt, Bauern, Jodler, Hermort,
doubled per fleck. A failed contract is won by the other side, so its
points count for them.
"""

import dataclasses
from typing import Optional, Sequence

NUM_SEATS = 4
SET_POINTS = 31
SETS_TO_WIN = 2


def caller_of(dealer: int) -> int:
  """The table seat of the Caller: the dealer's left (clockwise) neighbour."""
  return (dealer + 1) % NUM_SEATS


def table_seat(game_seat: int, dealer: int) -> int:
  """The table seat that plays game seat `game_seat` in a deal by `dealer`."""
  return (caller_of(dealer) + game_seat) % NUM_SEATS


def game_seat(seat: int, dealer: int) -> int:
  """The game seat table seat `seat` plays in a deal by `dealer`."""
  return (seat - caller_of(dealer)) % NUM_SEATS


def pair_of(seat: int) -> int:
  """The pair of a table seat: 0 for seats 0 and 2, 1 for seats 1 and 3."""
  return seat % 2


@dataclasses.dataclass(frozen=True)
class DealResult:
  """One finished deal, in table terms.

  Attributes:
    number: the deal's number in the match, from 1.
    set_number: the set it belongs to, from 1.
    dealer: the dealer's table seat.
    caller: the Caller's table seat.
    contract: "Normal", "Schnapser", "Lomt", "Bauern", "Jodler" or "Hermort".
    declarer: the declarer's table seat, None for a Normal game.
    flecks: the flecks on the contract.
    winner: the pair that won the deal.
    points: the points it won.
    need_after: each pair's points still needed after the deal (before a
      new set resets them).
    throw: the cardthrowup that ended the deal, or None: {"kind"
      ("resign"), "seat" (table seat), "text"} (docs/cardthrowup.md).
  """

  number: int
  set_number: int
  dealer: int
  caller: int
  contract: str
  declarer: Optional[int]
  flecks: int
  winner: int
  points: int
  need_after: tuple[int, int]
  throw: Optional[dict] = None

  def to_json(self) -> dict:
    return dataclasses.asdict(self)


def deal_winner(returns: Sequence[float], dealer: int) -> tuple[int, int]:
  """(winning pair, points) of a deal from the game's returns.

  Args:
    returns: the game seats' returns (zero-sum: +v for the winners).
    dealer: the dealer's table seat.

  Returns:
    The pair holding the winning game seats, and v.

  Raises:
    ValueError: no seat won (the game always has a winner).
  """
  best = max(range(NUM_SEATS), key=lambda g: returns[g])
  points = int(round(returns[best]))
  if points <= 0:
    raise ValueError(f"a deal without a winner: returns {list(returns)}")
  return pair_of(table_seat(best, dealer)), points


@dataclasses.dataclass
class Match:
  """The score of a match at one table (module doc).

  Attributes:
    dealer: the table seat dealing the current (or next) deal.
    need: points each pair still needs in the current set.
    sets: sets each pair has won.
    set_number: the current set, from 1.
    deals: every finished deal, oldest first.
    winner: the pair that won the match, None while it runs.
  """

  dealer: int
  need: list[int] = dataclasses.field(
      default_factory=lambda: [SET_POINTS, SET_POINTS]
  )
  sets: list[int] = dataclasses.field(default_factory=lambda: [0, 0])
  set_number: int = 1
  deals: list[DealResult] = dataclasses.field(default_factory=list)
  winner: Optional[int] = None

  @property
  def caller(self) -> int:
    """The Caller's table seat in the current deal."""
    return caller_of(self.dealer)

  def record(
      self,
      returns: Sequence[float],
      contract: str,
      declarer_game_seat: Optional[int],
      flecks: int,
      throw: Optional[dict] = None,
  ) -> dict:
    """Scores a finished deal and moves the dealer on.

    Args:
      returns: the game seats' returns.
      contract: the contract played.
      declarer_game_seat: the declarer's game seat (None for Normal).
      flecks: the flecks.
      throw: the throw that ended it (DealResult.throw), or None.

    Returns:
      {"deal": DealResult, "set_winner": pair or None, "match_winner": pair
      or None}.

    Raises:
      ValueError: the match is over.
    """
    if self.winner is not None:
      raise ValueError("the match is over")
    pair, points = deal_winner(returns, self.dealer)
    self.need[pair] -= points
    declarer = (
        None
        if declarer_game_seat is None or contract == "Normal"
        else table_seat(declarer_game_seat, self.dealer)
    )
    result = DealResult(
        number=len(self.deals) + 1,
        set_number=self.set_number,
        dealer=self.dealer,
        caller=self.caller,
        contract=contract,
        declarer=declarer,
        flecks=flecks,
        winner=pair,
        points=points,
        need_after=(self.need[0], self.need[1]),
        throw=throw,
    )
    self.deals.append(result)
    set_winner = match_winner = None
    if self.need[pair] <= 0:
      set_winner = pair
      self.sets[pair] += 1
      if self.sets[pair] >= SETS_TO_WIN:
        match_winner = self.winner = pair
      else:
        self.set_number += 1
        self.need = [SET_POINTS, SET_POINTS]
    self.dealer = (self.dealer + 1) % NUM_SEATS
    return {
        "deal": result,
        "set_winner": set_winner,
        "match_winner": match_winner,
    }

  def to_json(self) -> dict:
    return {
        "dealer": self.dealer,
        "caller": self.caller,
        "need": list(self.need),
        "sets": list(self.sets),
        "setNumber": self.set_number,
        "winner": self.winner,
        "deals": [d.to_json() for d in self.deals],
    }
