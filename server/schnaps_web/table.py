"""A table: four seats, its players and bots, a match, the current deal.

Life cycle (`phase`):

  open        waiting for players; the creator seats people or bots
  playing     a deal is in progress
  deal_over   the deal's result shows for settings.deal_pause seconds, or
              longer while a seated player holds "Wait" (`wait`): the next
              deal starts once the pause is over and nobody online waits
  match_over  a pair won two sets; the creator may start a new match

Seats are "empty", "human" (a nickname and a private seat token) or "bot".
Anyone may take an empty seat at any time (also in a running match); the
creator may put a bot into any seat but a human's, take a bot out (its seat
becomes empty) and start the match once all four seats are filled. If the
seat to move is empty or its player is offline, play simply waits.

During the card play a seated player may also throw their cards
(docs/cardthrowup.md): Resign or Allmine (`throw`), which ends the deal;
bots claim Allmine when the solver proves it, and never resign.

Privacy: a connection's view is chosen by its token (the seat it holds);
without one it is a spectator's. Nobody is ever sent another seat's hand.

Every change is pushed to every connection as a snapshot (`snapshot`). Bot
moves are played by one driver task per table, with settings.bot_delay
before each, the network running in a worker thread.
"""

import asyncio
import dataclasses
import random
import secrets
import time
from typing import Any, Awaitable, Callable, Optional

import pyspiel

from schnaps_web import config as config_lib
from schnaps_web import deal as deal_lib
from schnaps_web import match as match_lib

NAME_MAX = 20

# The languages a table can show (the client translates; i18n/strings.ts).
LANGS = ("it", "de", "en")
DEFAULT_LANG = "it"

#: First names a seated bot gets, one not yet used at its table.
BOT_NAMES = (
    "Harry", "Hermione", "Ron", "Ginny", "Neville", "Luna", "Fred", "George",
    "Percy", "Bill", "Charlie", "Molly", "Arthur", "Albus", "Minerva",
    "Severus", "Rubeus", "Sirius", "Remus", "Nymphadora", "Draco", "Lucius",
    "Narcissa", "Bellatrix", "Cedric", "Cho", "Dean", "Seamus", "Lavender",
    "Parvati", "Padma", "Oliver", "Viktor", "Fleur", "Dobby", "Kreacher",
    "Horace", "Filius", "Pomona", "Sybill", "Gilderoy", "Dolores", "Argus",
    "Poppy", "Kingsley", "Alastor", "Aberforth", "Dudley", "Petunia",
    "Vernon", "Myrtle", "Winky", "Griphook", "Xenophilius", "Tom",
)


#: The cardthrowups a seat may make (Table.throw).
THROWS = ("resign", "allmine")

#: The most solver nodes a bot's Allmine check may take (a few thousand at
#: most in practice; over the budget the bot just plays on).
BOT_CLAIM_BUDGET = 50_000


class TableError(ValueError):
  """A request the table refuses (bad seat, not allowed, wrong phase)."""


class Forbidden(TableError):
  """The token may not do this."""


def clean_lang(lang: Any) -> str:
  """One of LANGS; None (not given) is DEFAULT_LANG."""
  if lang is None:
    return DEFAULT_LANG
  if lang not in LANGS:
    raise TableError(f"unknown language {lang!r}")
  return lang


def clean_name(name: Any, what: str = "name") -> str:
  """A trimmed, non-empty name of at most NAME_MAX characters."""
  if not isinstance(name, str) or not name.strip():
    raise TableError(f"a {what} is required")
  name = " ".join(name.split())
  if len(name) > NAME_MAX:
    raise TableError(f"the {what} is longer than {NAME_MAX} characters")
  return name


@dataclasses.dataclass
class Seat:
  """One seat.

  Attributes:
    kind: "empty", "human" or "bot".
    name: the player's nickname or the bot's name (from BOT_NAMES).
    token: the human's seat token.
    bot: the bot's catalog name.
  """

  kind: str = "empty"
  name: str = ""
  token: Optional[str] = None
  bot: Optional[str] = None


@dataclasses.dataclass(eq=False)
class Listener:
  """One connection watching the table.

  Attributes:
    token: the token it connected with, or None (a spectator).
    send: sends one snapshot.
    reveal: a spectator on the all-cards watch port (sees every hand).
  """

  token: Optional[str]
  send: Callable[[dict], Awaitable[None]]
  reveal: bool = False


class Table:
  """A table (module doc).

  Attributes:
    id: the table id.
    name: its name.
    lang: the language its pages show ("it", "de" or "en").
    phase: the life-cycle phase.
    seats: the four seats.
    match: the match, None before the first start.
    deal: the current (or last) deal.
    last_result: the last deal's result for the overlay, or None.
    waiting: the seats holding the next deal back ("Wait"), between deals.
  """

  def __init__(
      self,
      table_id: str,
      name: str,
      bots: dict,
      settings: config_lib.Settings,
      game: pyspiel.Game,
      rng: Optional[random.Random] = None,
      lang: Optional[str] = None,
  ):
    self.id = table_id
    self.name = clean_name(name, "table name")
    self.lang = clean_lang(lang)
    self.phase = "open"
    self.seats = [Seat() for _ in range(match_lib.NUM_SEATS)]
    self.match: Optional[match_lib.Match] = None
    self.deal: Optional[deal_lib.Deal] = None
    self.last_result: Optional[dict] = None
    self.waiting: set[int] = set()
    self.closed = False
    self._next_deal_at = 0.0  # time.monotonic() when the pause ends
    self._bots = bots
    self._settings = settings
    self._game = game
    self._rng = rng or random.Random()
    self._creator: Optional[str] = None
    self._listeners: set[Listener] = set()
    self._task: Optional[asyncio.Task] = None

  # -- who is who ------------------------------------------------------------

  def seat_of(self, token: Optional[str]) -> Optional[int]:
    """The seat a token holds, or None."""
    if not token:
      return None
    for i, s in enumerate(self.seats):
      if s.kind == "human" and s.token == token:
        return i
    return None

  def is_creator(self, token: Optional[str]) -> bool:
    return bool(token) and token == self._creator

  def _require_creator(self, token: Optional[str]) -> None:
    if not self.is_creator(token):
      raise Forbidden("only the table's creator may do that")

  def _seat(self, seat: Any) -> Seat:
    if not isinstance(seat, int) or not 0 <= seat < match_lib.NUM_SEATS:
      raise TableError(f"no seat {seat!r}")
    return self.seats[seat]

  def online(self, seat: int) -> bool:
    """Whether the seat's player has a connection open (bots always do)."""
    s = self.seats[seat]
    if s.kind == "bot":
      return True
    if s.kind != "human":
      return False
    return any(l.token == s.token for l in self._listeners)

  # -- seats -----------------------------------------------------------------

  def sit(self, seat: int, name: str, creator: bool = False) -> str:
    """A human takes an empty seat; returns the new seat token."""
    s = self._seat(seat)
    if s.kind != "empty":
      raise TableError(f"seat {seat} is taken")
    token = secrets.token_urlsafe(16)
    self.seats[seat] = Seat("human", clean_name(name, "nickname"), token)
    if creator:
      self._creator = token
    self._changed()
    return token

  def set_bot(self, token: Optional[str], seat: int, bot: str) -> None:
    """The creator puts a bot into an empty seat, a bot's, or their own."""
    self._require_creator(token)
    s = self._seat(seat)
    if bot not in self._bots:
      raise TableError(f"no bot {bot!r}")
    if s.kind == "human" and s.token != token:
      raise TableError(f"seat {seat} has a player")
    self.seats[seat] = Seat("bot", self._bot_name(seat), None, bot)
    self.waiting.discard(seat)
    self._changed()

  def _bot_name(self, seat: int) -> str:
    """A random name from BOT_NAMES that no other seat uses."""
    taken = {s.name for i, s in enumerate(self.seats) if i != seat}
    free = [n for n in BOT_NAMES if n not in taken]
    return self._rng.choice(free or list(BOT_NAMES))

  def clear_seat(self, token: Optional[str], seat: int) -> None:
    """Empties a seat: the creator takes a bot out, or a player leaves."""
    s = self._seat(seat)
    if s.kind == "human" and s.token == token:
      pass  # a player leaves their own seat
    elif s.kind == "bot" and self.is_creator(token):
      pass
    else:
      raise Forbidden("you may not empty that seat")
    self.seats[seat] = Seat()
    self.waiting.discard(seat)
    self._changed()

  # -- play ------------------------------------------------------------------

  def start(self, token: Optional[str]) -> None:
    """The creator starts a match (open or match_over, all seats filled)."""
    self._require_creator(token)
    if self.phase not in ("open", "match_over"):
      raise TableError("a match is already running")
    if any(s.kind == "empty" for s in self.seats):
      raise TableError("every seat must be filled first")
    self.match = match_lib.Match(dealer=self._rng.randrange(4))
    self.last_result = None
    self._new_deal()

  def _new_deal(self) -> None:
    self.deal = deal_lib.Deal(self._game, self.match.dealer, self._rng)
    self.phase = "playing"
    self.waiting.clear()
    self._changed()

  def wait(self, token: Optional[str], on: Any) -> None:
    """The token's seat holds the next deal back (on) or lets it come (off).

    Only between deals (deal_over). The next deal starts once the pause is
    over and no online seat waits: when the last one lets go after the
    pause, at once.
    """
    seat = self.seat_of(token)
    if seat is None:
      raise Forbidden("you have no seat at this table")
    if not isinstance(on, bool):
      raise TableError("wait is true or false")
    if self.phase != "deal_over":
      raise TableError("no deal has just ended")
    if on:
      self.waiting.add(seat)
    else:
      self.waiting.discard(seat)
    self._changed()

  def _holding(self) -> list[int]:
    """The seats that hold the next deal back: waiting and online."""
    return sorted(s for s in self.waiting if self.online(s))

  def act(self, token: Optional[str], action: Any) -> None:
    """The token's seat plays `action` in the current deal."""
    seat = self.seat_of(token)
    if seat is None:
      raise Forbidden("you have no seat at this table")
    if self.phase != "playing":
      raise TableError("no deal is in progress")
    if not isinstance(action, int):
      raise TableError("an action is an integer")
    try:
      self.deal.apply(seat, action)
    except deal_lib.DealError as e:
      raise TableError(str(e)) from e
    self._changed()

  def throw(self, token: Optional[str], kind: Any) -> None:
    """The token's seat throws its cards: "resign" or "allmine".

    The same checks as act(), but not only on the seat's turn
    (docs/cardthrowup.md; deal.Deal.resign and claim). The deal is then
    over; the driver records it.
    """
    seat = self.seat_of(token)
    if seat is None:
      raise Forbidden("you have no seat at this table")
    if self.phase != "playing":
      raise TableError("no deal is in progress")
    if kind not in THROWS:
      raise TableError(f"a throw is one of {', '.join(THROWS)}")
    try:
      if kind == "resign":
        self.deal.resign(seat)
      else:
        self.deal.claim(seat)
    except deal_lib.DealError as e:
      raise TableError(str(e)) from e
    self._changed()

  def _finish_deal(self) -> None:
    res = self.deal.result()
    throw = None
    if res["throw"] is not None:
      t = res["throw"]
      throw = {
          "kind": t["kind"],
          "seat": self.deal.table_seat(t["seat"]),
          "accepted": t["accepted"],
          "text": t["text"],
      }
    out = self.match.record(
        res["returns"], res["contract"], res["declarer"], res["flecks"], throw
    )
    self.last_result = {
        "deal": out["deal"].to_json(),
        "setWinner": out["set_winner"],
        "matchWinner": out["match_winner"],
    }
    self.phase = "match_over" if out["match_winner"] is not None else "deal_over"
    self.waiting.clear()
    self._next_deal_at = time.monotonic() + self._settings.deal_pause
    self._changed()

  async def _drive(self) -> None:
    """Plays bot moves and moves between deals until a human must act."""
    while not self.closed:
      if self.phase == "deal_over":
        if self._holding():
          return  # wait() (or a waiting player leaving) wakes us
        delay = self._next_deal_at - time.monotonic()
        if delay > 0:
          await asyncio.sleep(delay)
          continue  # look again: someone may have pressed Wait meanwhile
        self._new_deal()
        continue
      if self.phase != "playing":
        return
      deal = self.deal
      if deal.is_over:
        self._finish_deal()
        continue
      seat = deal.to_move()
      s = self.seats[seat]
      if s.kind != "bot":
        return  # a human (or an empty seat) must act; act() wakes us
      await asyncio.sleep(self._settings.bot_delay)
      if self.closed or self.deal is not deal or deal.to_move() != seat:
        continue
      s = self.seats[seat]
      if s.kind != "bot":
        continue
      # A bot claims every remaining trick when the solver proves it
      # (docs/cardthrowup.md); it never resigns.
      if deal.claim_holds(seat, BOT_CLAIM_BUDGET):
        deal.claim(seat)
        self._changed()
        continue
      bot = self._bots[s.bot]
      moves = len(deal.state.history())
      action = await asyncio.to_thread(
          bot.choose, deal.state.clone(), deal.game_seat(seat), self.set_need()
      )
      if (
          self.deal is not deal
          or deal.is_over
          or len(deal.state.history()) != moves
      ):
        continue  # the table moved on meanwhile (a move, a throw)
      if self.seats[seat].kind != "bot":
        continue
      deal.apply(seat, action)
      self._changed()

  def set_need(self) -> Optional[tuple[int, int]]:
    """Points each game partnership still needs in the set (bots' view).

    Game partnership 0 is game seats 0 and 2 (the Caller's); it is the table
    pair of the Caller, which changes with the dealer. None without a deal.
    """
    if self.match is None or self.deal is None:
      return None
    caller_pair = match_lib.pair_of(match_lib.table_seat(0, self.deal.dealer))
    need = self.match.need
    return (need[caller_pair], need[1 - caller_pair])

  def _wake(self) -> None:
    if self.closed:
      return
    if self._task is None or self._task.done():
      try:
        loop = asyncio.get_running_loop()
      except RuntimeError:
        return  # no loop (plain unit use): nothing to drive
      self._task = loop.create_task(self._drive())

  def close(self, token: Optional[str]) -> None:
    self._require_creator(token)
    self.closed = True
    self.phase = "closed"
    self._changed()

  # -- views -----------------------------------------------------------------

  def summary(self) -> dict:
    """The lobby's line for this table (no hidden information)."""
    return {
        "id": self.id,
        "name": self.name,
        "lang": self.lang,
        "phase": self.phase,
        "seats": [self._seat_json(i, None) for i in range(4)],
        "need": list(self.match.need) if self.match else None,
        "sets": list(self.match.sets) if self.match else None,
    }

  def _seat_json(self, i: int, token: Optional[str]) -> dict:
    s = self.seats[i]
    return {
        "kind": s.kind,
        "name": s.name,
        "bot": s.bot,
        "botLabel": self._bots[s.bot].label if s.bot in self._bots else None,
        "online": self.online(i),
        "you": s.kind == "human" and token is not None and s.token == token,
    }

  def snapshot(self, token: Optional[str], reveal: bool = False) -> dict:
    """Everything the holder of `token` (None: a spectator) may see.

    `reveal`: a spectator on the watch port, who sees every hand (a token
    is ignored there).
    """
    seat = None if reveal else self.seat_of(token)
    if reveal:
      token = None
    return {
        "type": "table",
        "id": self.id,
        "name": self.name,
        "lang": self.lang,
        "phase": self.phase,
        "you": seat,
        "isCreator": self.is_creator(token),
        "seats": [self._seat_json(i, token) for i in range(4)],
        "match": self.match.to_json() if self.match else None,
        "dealer": self.deal.dealer if self.deal else None,
        "toMove": self.deal.to_move() if self.deal else None,
        "frame": self.deal.frame(seat, reveal) if self.deal else None,
        "reveal": reveal,
        "lastResult": self.last_result,
        "waiting": self._holding() if self.phase == "deal_over" else [],
        "bots": [{"name": b.name, "label": b.label} for b in self._bots.values()],
    }

  # -- connections -----------------------------------------------------------

  async def attach(self, listener: Listener) -> None:
    self._listeners.add(listener)
    self._changed()

  def detach(self, listener: Listener) -> None:
    self._listeners.discard(listener)
    self._changed()

  def _changed(self) -> None:
    """Pushes a snapshot to every connection and wakes the driver."""
    try:
      loop = asyncio.get_running_loop()
    except RuntimeError:
      loop = None
    if loop is not None:
      for l in list(self._listeners):
        loop.create_task(self._send(l))
    self._wake()

  async def _send(self, listener: Listener) -> None:
    try:
      await listener.send(self.snapshot(listener.token, listener.reveal))
    except Exception:  # pylint: disable=broad-except
      self._listeners.discard(listener)
