"""The site's small database: users, pair ratings and a log of past sets.

One SQLite file, schnaps.db, in settings.db_dir (by default data/db/;
empty: an in-memory database, for tests). Tables:

  users        lower (the lower-case username, primary key), name, created,
               salt, hash, iterations
  device_keys  hash (SHA-256 of a device key, primary key), user (users.
               lower), created
  pairs        key (rating.py's pair key), members (JSON list), rating,
               won, lost, last
  sets         one row per finished set (Db.record_set): id, time, match,
               table_name, rated (0/1), and entry, the whole set as JSON:
               when, the table, the match id, the four players, every deal
               of the set, the winner and the rating change. It is the
               history: the pairs can be rebuilt from it (Db.rebuild_ratings).

Accounts: a username and a password (PBKDF2-SHA256, salted). Registering
or logging in gives the browser a device key, a long random token; the
server keeps only its SHA-256. With the key a device plays as that user
without the password again, until it logs out.

A finished set's log row and its rating change are written in one
transaction. One server process owns the file. Keep it on a local disk
(not a network share: SQLite needs working file locks).

Before SQLite the database was three JSON files in the same directory
(users.json, ratings.json, sets.jsonl). When schnaps.db does not exist yet
and those files do, they are imported once (Db.import_json) and then left
alone, as a backup.
"""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from typing import Any, Optional

from schnaps_web import rating as rating_lib

USERNAME_MAX = 20
PASSWORD_MIN = 4
PASSWORD_MAX = 200
ITERATIONS = 200_000

#: The database file's name in the directory.
FILE = "schnaps.db"

#: The schema's version (PRAGMA user_version).
SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  lower      TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  created    TEXT NOT NULL,
  salt       TEXT NOT NULL,
  hash       TEXT NOT NULL,
  iterations INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS device_keys (
  hash    TEXT PRIMARY KEY,
  user    TEXT NOT NULL REFERENCES users(lower) ON DELETE CASCADE,
  created TEXT
);
CREATE INDEX IF NOT EXISTS device_keys_user ON device_keys(user);
CREATE TABLE IF NOT EXISTS pairs (
  key     TEXT PRIMARY KEY,
  members TEXT NOT NULL,
  rating  REAL NOT NULL,
  won     INTEGER NOT NULL,
  lost    INTEGER NOT NULL,
  last    TEXT
);
CREATE TABLE IF NOT EXISTS sets (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  time       TEXT NOT NULL,
  match      TEXT,
  table_name TEXT,
  rated      INTEGER NOT NULL,
  entry      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sets_time ON sets(time);
"""


class AccountError(ValueError):
  """A registration or login the database refuses."""


def now() -> str:
  """The time in UTC, ISO 8601 to the second."""
  return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _hash_password(password: str, salt: bytes, iterations: int) -> str:
  return hashlib.pbkdf2_hmac(
      "sha256", password.encode(), salt, iterations
  ).hex()


def _hash_key(key: str) -> str:
  return hashlib.sha256(key.encode()).hexdigest()


def _lower(name: str) -> str:
  return " ".join(name.split()).lower()


def clean_username(name: Any) -> str:
  """A trimmed username: not empty, at most USERNAME_MAX characters, no "+"."""
  if not isinstance(name, str) or not name.strip():
    raise AccountError("a username is required")
  name = " ".join(name.split())
  if len(name) > USERNAME_MAX:
    raise AccountError(
        f"the username is longer than {USERNAME_MAX} characters"
    )
  if "+" in name:
    raise AccountError("a username may not contain +")
  return name


class Db:
  """The database (module doc).

  Args:
    directory: where schnaps.db lives; None or "": in memory only.
  """

  def __init__(self, directory: Optional[str] = None):
    self._dir = directory or None
    # The site calls the database from the event loop; the lock keeps it
    # safe should a call ever come from a worker thread.
    self._lock = threading.RLock()
    if self._dir:
      os.makedirs(self._dir, exist_ok=True)
      path = os.path.join(self._dir, FILE)
      fresh = not os.path.exists(path)
    else:
      path, fresh = ":memory:", False
    self._conn = sqlite3.connect(path, check_same_thread=False)
    self._conn.row_factory = sqlite3.Row
    self._conn.execute("PRAGMA foreign_keys = ON")
    self._conn.executescript(_SCHEMA)
    self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    self._conn.commit()
    if fresh and self._has_json(self._dir):
      counts = self.import_json(self._dir)
      print(
          f"Database: imported {counts['users']} users, {counts['pairs']} "
          f"pairs and {counts['sets']} sets from the JSON files into "
          f"{path} (the JSON files are kept, but no longer used).",
          flush=True,
      )

  def close(self) -> None:
    """Closes the file (the object is unusable afterwards)."""
    with self._lock:
      self._conn.close()

  # -- the JSON files from before SQLite -------------------------------------

  @staticmethod
  def _has_json(directory: str) -> bool:
    return any(
        os.path.exists(os.path.join(directory, n))
        for n in ("users.json", "ratings.json", "sets.jsonl")
    )

  def import_json(self, directory: str) -> dict:
    """Imports users.json, ratings.json and sets.jsonl from `directory`.

    Missing files are skipped. Runs in one transaction; the pairs are taken
    as stored (not rebuilt from the log).

    Returns:
      {"users", "pairs", "sets"}: how many of each were imported.
    """

    def load(name: str) -> dict:
      try:
        with open(os.path.join(directory, name), encoding="utf-8") as f:
          return json.load(f)
      except FileNotFoundError:
        return {}

    users = load("users.json").get("users", {})
    pairs = load("ratings.json").get("pairs", {})
    try:
      with open(os.path.join(directory, "sets.jsonl"), encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
      entries = []
    with self._lock, self._conn:
      for lower, u in users.items():
        self._conn.execute(
            "INSERT INTO users (lower, name, created, salt, hash, iterations)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (lower, u["name"], u["created"], u["salt"], u["hash"],
             u["iterations"]),
        )
        self._conn.executemany(
            "INSERT OR IGNORE INTO device_keys (hash, user, created)"
            " VALUES (?, ?, NULL)",
            [(h, lower) for h in u.get("keys", [])],
        )
      for key, p in pairs.items():
        self._put_pair(key, p)
      for entry in entries:
        self._insert_set(entry)
    return {"users": len(users), "pairs": len(pairs), "sets": len(entries)}

  # -- users -----------------------------------------------------------------

  def _user(self, lower: str) -> Optional[sqlite3.Row]:
    return self._conn.execute(
        "SELECT * FROM users WHERE lower = ?", (lower,)
    ).fetchone()

  def register(self, username: Any, password: Any) -> tuple[str, str]:
    """A new account; returns (username, device key)."""
    name = clean_username(username)
    if self.is_registered(name):
      raise AccountError("that username is taken")
    if not isinstance(password, str) or len(password) < PASSWORD_MIN:
      raise AccountError(
          f"the password needs at least {PASSWORD_MIN} characters"
      )
    if len(password) > PASSWORD_MAX:
      raise AccountError("the password is too long")
    salt = secrets.token_bytes(16)
    hashed = _hash_password(password, salt, ITERATIONS)
    with self._lock:
      try:
        with self._conn:
          self._conn.execute(
              "INSERT INTO users (lower, name, created, salt, hash,"
              " iterations) VALUES (?, ?, ?, ?, ?, ?)",
              (name.lower(), name, now(), salt.hex(), hashed, ITERATIONS),
          )
      except sqlite3.IntegrityError:
        raise AccountError("that username is taken") from None
      return name, self._new_key(name.lower())

  def login(self, username: Any, password: Any) -> tuple[str, str]:
    """Checks the password; returns (username, a new device key)."""
    with self._lock:
      user = self._user(_lower(username)) if isinstance(username, str) else None
    if user is None or not isinstance(password, str) or not hmac.compare_digest(
        user["hash"],
        _hash_password(password, bytes.fromhex(user["salt"]), user["iterations"]),
    ):
      raise AccountError("wrong username or password")
    with self._lock:
      return user["name"], self._new_key(user["lower"])

  def _new_key(self, lower: str) -> str:
    key = secrets.token_urlsafe(24)
    with self._lock, self._conn:
      self._conn.execute(
          "INSERT INTO device_keys (hash, user, created) VALUES (?, ?, ?)",
          (_hash_key(key), lower, now()),
      )
    return key

  def user_of_key(self, key: Optional[str]) -> Optional[str]:
    """The username a device key belongs to, or None."""
    if not key:
      return None
    with self._lock:
      row = self._conn.execute(
          "SELECT users.name FROM device_keys JOIN users"
          " ON users.lower = device_keys.user WHERE device_keys.hash = ?",
          (_hash_key(key),),
      ).fetchone()
    return row["name"] if row else None

  def logout(self, key: Optional[str]) -> None:
    """Forgets a device key (the device then needs the password again)."""
    if not key:
      return
    with self._lock, self._conn:
      self._conn.execute(
          "DELETE FROM device_keys WHERE hash = ?", (_hash_key(key),)
      )

  def is_registered(self, name: str) -> bool:
    """Whether `name` (any case) is someone's username."""
    with self._lock:
      return self._user(_lower(name)) is not None

  def _names(self) -> dict[str, str]:
    """Every user's lower-case username -> username."""
    return {
        r["lower"]: r["name"]
        for r in self._conn.execute("SELECT lower, name FROM users")
    }

  def name_of(self, identity: str) -> str:
    """What a rating identity shows: the username, or the bot's label."""
    with self._lock:
      return self._name_of(identity, None)

  def _name_of(self, identity: str, names: Optional[dict]) -> str:
    if identity.startswith(rating_lib.USER):
      lower = identity[len(rating_lib.USER):]
      if names is None:
        user = self._user(lower)
        return user["name"] if user else lower
      return names.get(lower, lower)
    return rating_lib.bot_label(identity[len(rating_lib.BOT):])

  # -- ratings ---------------------------------------------------------------

  def _pair(self, key: str) -> Optional[sqlite3.Row]:
    return self._conn.execute(
        "SELECT * FROM pairs WHERE key = ?", (key,)
    ).fetchone()

  def _put_pair(self, key: str, p: dict) -> None:
    self._conn.execute(
        "INSERT OR REPLACE INTO pairs (key, members, rating, won, lost, last)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (key, json.dumps(p["members"]), p["rating"], p["won"], p["lost"],
         p["last"]),
    )

  def rating(self, key: str) -> float:
    """A pair's rating (rating.START while it has played no rated set)."""
    with self._lock:
      pair = self._pair(key)
    return pair["rating"] if pair else rating_lib.START

  def record_set(self, entry: dict) -> dict:
    """Logs a finished set and, when it is rated, updates both pairs.

    Args:
      entry: the set (module doc, sets), with "pairs" (the keys of pair 0
        and pair 1, or None when the set is not rated) and "winner" (0 or
        1).

    Returns:
      The logged entry, with "time" and "ratings": {"before": [r0, r1],
      "after": [r0, r1]} (None when not rated).
    """
    entry = dict(entry, time=entry.get("time") or now(), ratings=None)
    with self._lock, self._conn:
      if entry.get("pairs"):
        entry["ratings"] = self._apply(
            entry["pairs"], entry["winner"], entry["time"]
        )
      self._insert_set(entry)
    return entry

  def _apply(self, pairs, winner: int, when: str) -> dict:
    """Updates both pairs' rows (inside the caller's transaction)."""
    before = [self.rating(k) for k in pairs]
    w, l = rating_lib.update(before[winner], before[1 - winner])
    after = [0.0, 0.0]
    after[winner], after[1 - winner] = w, l
    for i, key in enumerate(pairs):
      row = self._pair(key)
      pair = (
          {"members": json.loads(row["members"]), "won": row["won"],
           "lost": row["lost"]}
          if row else
          {"members": rating_lib.members(key), "won": 0, "lost": 0}
      )
      pair["rating"] = after[i]
      pair["won" if i == winner else "lost"] += 1
      pair["last"] = when
      self._put_pair(key, pair)
    return {"before": before, "after": after}

  def _insert_set(self, entry: dict) -> None:
    self._conn.execute(
        "INSERT INTO sets (time, match, table_name, rated, entry)"
        " VALUES (?, ?, ?, ?, ?)",
        (entry.get("time") or now(), entry.get("match"), entry.get("table"),
         1 if entry.get("ratings") else 0,
         json.dumps(entry, ensure_ascii=False, sort_keys=True)),
    )

  def sets(self) -> list[dict]:
    """Every logged set, oldest first."""
    with self._lock:
      rows = self._conn.execute("SELECT entry FROM sets ORDER BY id").fetchall()
    return [json.loads(r["entry"]) for r in rows]

  def rebuild_ratings(self) -> None:
    """Recomputes every pair's rating from the log (the sets table)."""
    entries = self.sets()
    with self._lock, self._conn:
      self._conn.execute("DELETE FROM pairs")
      for entry in entries:
        if entry.get("pairs"):
          self._apply(entry["pairs"], entry["winner"], entry["time"])

  def standings(self) -> list[dict]:
    """Every rated pair, best first: {"key", "players": [{"name", "bot"}],
    "rating" (rounded), "won", "lost", "last"}."""
    with self._lock:
      names = self._names()
      rows = self._conn.execute("SELECT * FROM pairs").fetchall()
    out = []
    for row in rows:
      out.append({
          "key": row["key"],
          "players": [
              {"name": self._name_of(m, names),
               "bot": m.startswith(rating_lib.BOT)}
              for m in json.loads(row["members"])
          ],
          "rating": round(row["rating"]),
          "won": row["won"],
          "lost": row["lost"],
          "last": row["last"],
      })
    out.sort(key=lambda p: (-p["rating"], -(p["won"] + p["lost"]), p["key"]))
    return out
