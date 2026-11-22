"""The site's small database: users, pair ratings and a log of past sets.

Plain files in one directory (settings.db_dir, by default data/db/; empty:
kept in memory only, for tests):

  users.json    {"users": {<lower-case username>: {"name", "created",
                "salt", "hash", "iterations", "keys": [sha256 of each
                device key]}}}
  ratings.json  {"pairs": {<pair key>: {"members", "rating", "won", "lost",
                "last"}}} (rating.py: pair keys and Elo)
  sets.jsonl    one JSON line per finished set (Db.record_set): when, the
                table, the match id, the four players, every deal of the
                set, the winner and the rating change. It is the history:
                ratings.json can be rebuilt from it (Db.rebuild_ratings).

Accounts: a username and a password (PBKDF2-SHA256, salted). Registering
or logging in gives the browser a device key, a long random token; the
server keeps only its SHA-256. With the key a device plays as that user
without the password again, until it logs out.

The JSON files are rewritten whole (to a temporary file, then renamed), so
a crash never leaves half a file. One server process owns the directory.
"""

import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Optional

from schnaps_web import rating as rating_lib

USERNAME_MAX = 20
PASSWORD_MIN = 4
PASSWORD_MAX = 200
ITERATIONS = 200_000


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
    directory: where the files live; None or "": in memory only.
  """

  def __init__(self, directory: Optional[str] = None):
    self._dir = directory or None
    self._users: dict[str, dict] = {}
    self._pairs: dict[str, dict] = {}
    self._sets: list[dict] = []  # in memory only (no directory)
    if self._dir:
      os.makedirs(self._dir, exist_ok=True)
      self._users = self._load("users.json").get("users", {})
      self._pairs = self._load("ratings.json").get("pairs", {})

  # -- files -----------------------------------------------------------------

  def _path(self, name: str) -> str:
    return os.path.join(self._dir, name)

  def _load(self, name: str) -> dict:
    try:
      with open(self._path(name), encoding="utf-8") as f:
        return json.load(f)
    except FileNotFoundError:
      return {}

  def _save(self, name: str, data: dict) -> None:
    if not self._dir:
      return
    tmp = self._path(name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, self._path(name))

  def _save_users(self) -> None:
    self._save("users.json", {"users": self._users})

  def _save_pairs(self) -> None:
    self._save("ratings.json", {"pairs": self._pairs})

  # -- users -----------------------------------------------------------------

  def register(self, username: Any, password: Any) -> tuple[str, str]:
    """A new account; returns (username, device key)."""
    name = clean_username(username)
    if name.lower() in self._users:
      raise AccountError("that username is taken")
    if not isinstance(password, str) or len(password) < PASSWORD_MIN:
      raise AccountError(
          f"the password needs at least {PASSWORD_MIN} characters"
      )
    if len(password) > PASSWORD_MAX:
      raise AccountError("the password is too long")
    salt = secrets.token_bytes(16)
    self._users[name.lower()] = {
        "name": name,
        "created": now(),
        "salt": salt.hex(),
        "iterations": ITERATIONS,
        "hash": _hash_password(password, salt, ITERATIONS),
        "keys": [],
    }
    return name, self._new_key(name.lower())

  def login(self, username: Any, password: Any) -> tuple[str, str]:
    """Checks the password; returns (username, a new device key)."""
    user = (
        self._users.get(" ".join(username.split()).lower())
        if isinstance(username, str)
        else None
    )
    if user is None or not isinstance(password, str) or not hmac.compare_digest(
        user["hash"],
        _hash_password(password, bytes.fromhex(user["salt"]), user["iterations"]),
    ):
      raise AccountError("wrong username or password")
    return user["name"], self._new_key(user["name"].lower())

  def _new_key(self, lower: str) -> str:
    key = secrets.token_urlsafe(24)
    self._users[lower]["keys"].append(_hash_key(key))
    self._save_users()
    return key

  def user_of_key(self, key: Optional[str]) -> Optional[str]:
    """The username a device key belongs to, or None."""
    if not key:
      return None
    hashed = _hash_key(key)
    for user in self._users.values():
      if hashed in user["keys"]:
        return user["name"]
    return None

  def logout(self, key: Optional[str]) -> None:
    """Forgets a device key (the device then needs the password again)."""
    if not key:
      return
    hashed = _hash_key(key)
    for user in self._users.values():
      if hashed in user["keys"]:
        user["keys"].remove(hashed)
        self._save_users()
        return

  def is_registered(self, name: str) -> bool:
    """Whether `name` (any case) is someone's username."""
    return " ".join(name.split()).lower() in self._users

  def name_of(self, identity: str) -> str:
    """What a rating identity shows: the username, or the bot's label."""
    if identity.startswith(rating_lib.USER):
      user = self._users.get(identity[len(rating_lib.USER):])
      return user["name"] if user else identity[len(rating_lib.USER):]
    return rating_lib.bot_label(identity[len(rating_lib.BOT):])

  # -- ratings ---------------------------------------------------------------

  def rating(self, key: str) -> float:
    """A pair's rating (rating.START while it has played no rated set)."""
    pair = self._pairs.get(key)
    return pair["rating"] if pair else rating_lib.START

  def record_set(self, entry: dict) -> dict:
    """Logs a finished set and, when it is rated, updates both pairs.

    Args:
      entry: the set (module doc, sets.jsonl), with "pairs" (the keys of
        pair 0 and pair 1, or None when the set is not rated) and "winner"
        (0 or 1).

    Returns:
      The logged entry, with "time" and "ratings": {"before": [r0, r1],
      "after": [r0, r1]} (None when not rated).
    """
    entry = dict(entry, time=entry.get("time") or now(), ratings=None)
    if entry.get("pairs"):
      entry["ratings"] = self._apply(entry["pairs"], entry["winner"], entry["time"])
      self._save_pairs()
    self._append(entry)
    return entry

  def _apply(self, pairs, winner: int, when: str) -> dict:
    before = [self.rating(k) for k in pairs]
    w, l = rating_lib.update(before[winner], before[1 - winner])
    after = [0.0, 0.0]
    after[winner], after[1 - winner] = w, l
    for i, key in enumerate(pairs):
      pair = self._pairs.setdefault(
          key,
          {"members": rating_lib.members(key), "rating": rating_lib.START,
           "won": 0, "lost": 0, "last": None},
      )
      pair["rating"] = after[i]
      pair["won" if i == winner else "lost"] += 1
      pair["last"] = when
    return {"before": before, "after": after}

  def _append(self, entry: dict) -> None:
    if not self._dir:
      self._sets.append(entry)
      return
    with open(self._path("sets.jsonl"), "a", encoding="utf-8") as f:
      f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

  def sets(self) -> list[dict]:
    """Every logged set, oldest first."""
    if not self._dir:
      return list(self._sets)
    try:
      with open(self._path("sets.jsonl"), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
      return []

  def rebuild_ratings(self) -> None:
    """Recomputes every pair's rating from the log (sets.jsonl)."""
    self._pairs = {}
    for entry in self.sets():
      if entry.get("pairs"):
        self._apply(entry["pairs"], entry["winner"], entry["time"])
    self._save_pairs()

  def standings(self) -> list[dict]:
    """Every rated pair, best first: {"key", "players": [{"name", "bot"}],
    "rating" (rounded), "won", "lost", "last"}."""
    out = []
    for key, pair in self._pairs.items():
      out.append({
          "key": key,
          "players": [
              {"name": self.name_of(m), "bot": m.startswith(rating_lib.BOT)}
              for m in pair["members"]
          ],
          "rating": round(pair["rating"]),
          "won": pair["won"],
          "lost": pair["lost"],
          "last": pair["last"],
      })
    out.sort(key=lambda p: (-p["rating"], -(p["won"] + p["lost"]), p["key"]))
    return out
