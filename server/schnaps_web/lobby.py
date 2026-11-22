"""The lobby: every table on the site, in memory."""

import random
import secrets
from typing import Optional

import pyspiel

from schnaps_web import config as config_lib
from schnaps_web import db as db_lib
from schnaps_web import deal as deal_lib
from schnaps_web import table as table_lib


class Lobby:
  """The tables (module doc).

  Attributes:
    tables: {id: Table}.
  """

  def __init__(
      self,
      bots: dict,
      settings: config_lib.Settings,
      rng: Optional[random.Random] = None,
      db: Optional[db_lib.Db] = None,
  ):
    self.tables: dict[str, table_lib.Table] = {}
    self.db = db if db is not None else db_lib.Db(settings.db_dir)
    self._bots = bots
    self._settings = settings
    self._game = pyspiel.load_game(deal_lib.GAME_STRING)
    self._rng = rng or random.Random()

  def create(
      self,
      name: str,
      player: str,
      seat: int,
      lang: Optional[str] = None,
      user: Optional[str] = None,
  ) -> tuple[table_lib.Table, str]:
    """A new table with its creator at `seat`; returns (table, token).

    `lang`: the language the table shows (table.LANGS; None: Italian).
    `user`: the creator's username when logged in (then `player` is it).
    """
    self._prune()
    if len(self.tables) >= self._settings.max_tables:
      raise table_lib.TableError("too many tables; close one first")
    player = table_lib.clean_name(player, "nickname")
    table_id = secrets.token_urlsafe(6)
    table = table_lib.Table(
        table_id,
        name,
        self._bots,
        self._settings,
        self._game,
        random.Random(self._rng.random()),
        lang=lang,
        db=self.db,
    )
    token = table.sit(seat, player, creator=True, user=user)
    self.tables[table_id] = table
    return table, token

  def get(self, table_id: str) -> table_lib.Table:
    table = self.tables.get(table_id)
    if table is None or table.closed:
      raise KeyError(table_id)
    return table

  def summaries(self) -> list[dict]:
    self._prune()
    return [t.summary() for t in self.tables.values()]

  def _prune(self) -> None:
    for tid in [tid for tid, t in self.tables.items() if t.closed]:
      del self.tables[tid]
