"""Accounts, pair ratings and the log of sets (db.py, rating.py, table.py)."""

import dataclasses
import json
import random
import sqlite3
import time

from fastapi import testclient
import pyspiel
import pytest

from schnaps_web import app as app_lib
from schnaps_web import bots as bots_lib
from schnaps_web import config as config_lib
from schnaps_web import db as db_lib
from schnaps_web import deal as deal_lib
from schnaps_web import rating as rating_lib
from schnaps_web import table as table_lib

FAST = config_lib.Settings(bot_delay=0.0, deal_pause=0.0, client_dir="/nonexistent")


def _bots():
  """Two bot kinds, so bot pairs can differ."""
  a = bots_lib.RandomBot(seed=1)
  b = bots_lib.RandomBot(seed=2)
  b.name, b.label = "random2", "Random2"
  return {"random": a, "random2": b}


# -- Elo ---------------------------------------------------------------------


def test_elo_equal_pairs_move_by_half_k():
  assert rating_lib.expected(600, 600) == 0.5
  assert rating_lib.update(600, 600) == (616.0, 584.0)


def test_elo_upset_moves_more_and_is_zero_sum():
  fav_wins = rating_lib.update(800, 600)
  upset = rating_lib.update(600, 800)
  assert fav_wins[0] - 800 < upset[0] - 600
  for w, l in ((800, 600), (600, 800), (612.5, 590.25)):
    nw, nl = rating_lib.update(w, l)
    assert nw + nl == pytest.approx(w + l)


def test_pair_keys_ignore_order_and_need_identities():
  anna, basic = rating_lib.user_id("Anna"), rating_lib.bot_id("basic")
  assert anna == "u:anna" and basic == "b:basic"
  assert rating_lib.pair_key(anna, basic) == rating_lib.pair_key(basic, anna)
  assert rating_lib.members(rating_lib.pair_key(anna, basic)) == [basic, anna]
  lineup = (anna, "b:large", basic, "u:ben")
  assert rating_lib.lineup_pairs(lineup) == ("b:basic+u:anna", "b:large+u:ben")
  assert rating_lib.lineup_pairs((anna, None, basic, "u:ben")) is None


# -- the database --------------------------------------------------------------


def test_register_login_device_keys_and_logout():
  db = db_lib.Db()
  name, key = db.register("  Anna  ", "secret")
  assert name == "Anna" and db.user_of_key(key) == "Anna"
  assert db.is_registered("anna") and not db.is_registered("Ben")
  with pytest.raises(db_lib.AccountError, match="taken"):
    db.register("ANNA", "other1")
  with pytest.raises(db_lib.AccountError, match="at least 4"):
    db.register("Ben", "abc")
  with pytest.raises(db_lib.AccountError, match="may not contain"):
    db.register("A+B", "secret")
  with pytest.raises(db_lib.AccountError, match="required"):
    db.register(" ", "secret")
  with pytest.raises(db_lib.AccountError, match="wrong username or password"):
    db.login("Anna", "wrong")
  with pytest.raises(db_lib.AccountError, match="wrong username or password"):
    db.login("Nobody", "secret")
  # A second device logs in; both keys work until one logs out.
  _, key2 = db.login("anna", "secret")
  assert key2 != key and db.user_of_key(key2) == "Anna"
  db.logout(key)
  assert db.user_of_key(key) is None and db.user_of_key(key2) == "Anna"
  assert db.user_of_key("made-up") is None and db.user_of_key(None) is None


def test_the_files_survive_a_restart_and_keep_no_secrets(tmp_path):
  db = db_lib.Db(str(tmp_path))
  _, key = db.register("Anna", "secret")
  db.record_set({"pairs": ["b:basic+u:anna", "b:large+b:large"], "winner": 0,
                 "deals": [{"number": 1}]})
  again = db_lib.Db(str(tmp_path))
  assert again.user_of_key(key) == "Anna"
  assert again.login("Anna", "secret")[0] == "Anna"
  assert again.rating("b:basic+u:anna") == 616.0
  stored = (tmp_path / "schnaps.db").read_bytes()
  assert b"secret" not in stored and key.encode() not in stored
  assert sorted(p.name for p in tmp_path.iterdir()) == ["schnaps.db"]
  (line,) = again.sets()
  assert line["deals"] == [{"number": 1}] and line["ratings"]["after"] == [616.0, 584.0]


def test_the_json_files_from_before_sqlite_are_imported_once(tmp_path):
  salt = bytes(range(16))
  key_hash = db_lib._hash_key("old-device-key")
  (tmp_path / "users.json").write_text(json.dumps({"users": {"anna": {
      "name": "Anna", "created": "2026-11-20T10:00:00Z", "salt": salt.hex(),
      "iterations": 1000, "hash": db_lib._hash_password("secret", salt, 1000),
      "keys": [key_hash]}}}))
  ab = "b:basic+u:anna"
  (tmp_path / "ratings.json").write_text(json.dumps({"pairs": {ab: {
      "members": ["b:basic", "u:anna"], "rating": 616.0, "won": 1, "lost": 0,
      "last": "2026-11-21T10:00:00Z"}}}))
  logged = [{"time": "2026-11-21T10:00:00Z", "table": "T", "match": "m1",
             "pairs": [ab, "b:large+b:large"], "winner": 0,
             "ratings": {"before": [600.0, 600.0], "after": [616.0, 584.0]}},
            {"time": "2026-11-21T11:00:00Z", "pairs": None, "winner": 1,
             "ratings": None, "unrated": "guest"}]
  (tmp_path / "sets.jsonl").write_text(
      "".join(json.dumps(e) + "\n" for e in logged))
  db = db_lib.Db(str(tmp_path))
  assert db.user_of_key("old-device-key") == "Anna"
  assert db.login("anna", "secret")[0] == "Anna"
  assert db.rating(ab) == 616.0
  assert db.standings()[0]["players"][1] == {"name": "Anna", "bot": False}
  assert db.sets() == logged
  db.close()
  # The JSON files stay as a backup, and a second start doesn't import again.
  assert sorted(p.name for p in tmp_path.iterdir()) == [
      "ratings.json", "schnaps.db", "sets.jsonl", "users.json"]
  assert len(db_lib.Db(str(tmp_path)).sets()) == 2


def test_standings_and_rebuilding_from_the_log(tmp_path):
  db = db_lib.Db(str(tmp_path))
  db.register("Anna", "secret")
  ab, ll = "b:basic+u:anna", "b:large+b:large"
  for winner in (0, 0, 1):
    db.record_set({"pairs": [ab, ll], "winner": winner})
  db.record_set({"pairs": None, "winner": 0, "unrated": "guest"})
  table = db.standings()
  assert [p["key"] for p in table] == [ab, ll]
  top = table[0]
  assert (top["won"], top["lost"]) == (2, 1)
  assert top["players"] == [{"name": "Bologna", "bot": True}, {"name": "Anna", "bot": False}]
  assert top["rating"] + table[1]["rating"] == 1200
  before = {p["key"]: p["rating"] for p in table}
  db.close()
  conn = sqlite3.connect(tmp_path / "schnaps.db")
  with conn:
    conn.execute("DELETE FROM pairs")
  conn.close()
  fresh = db_lib.Db(str(tmp_path))
  assert fresh.standings() == []
  fresh.rebuild_ratings()
  assert {p["key"]: p["rating"] for p in fresh.standings()} == before
  assert len(fresh.sets()) == 4


# -- the table: which sets count ---------------------------------------------------


def _table(db, bots=None):
  game = pyspiel.load_game(deal_lib.GAME_STRING)
  return table_lib.Table("t", "T", bots or _bots(), FAST, game,
                         random.Random(0), db=db)


def _play_set(t, rng):
  """Plays random moves (no event loop: no driver) until a set ends."""
  sets = list(t.match.sets)
  while list(t.match.sets) == sets:
    if t.phase == "deal_over":
      t._new_deal()  # pylint: disable=protected-access
    d = t.deal
    d.apply(d.to_move(), rng.choice(d.state.legal_actions()))
    if d.is_over:
      t._finish_deal()  # pylint: disable=protected-access
  return t.last_result["rating"]


def test_a_set_of_users_and_bots_is_rated_and_logged():
  db = db_lib.Db()
  db.register("Anna", "secret")
  db.register("Ben", "secret")
  t = _table(db)
  anna = t.sit(0, "Anna", creator=True, user="Anna")
  t.sit(1, "Ben", user="Ben")
  t.set_bot(anna, 2, "random")
  t.set_bot(anna, 3, "random2")
  assert t.pair_ratings() == [600, 600]
  t.start(anna)
  r = _play_set(t, random.Random(3))
  assert r["rated"] and r["unrated"] is None
  w = t.last_result["setWinner"]
  assert r["before"] == [600, 600] and r["after"][w] == 616 and r["after"][1 - w] == 584
  assert t.pair_ratings() == r["after"]
  (entry,) = db.sets()
  assert entry["pairs"] == ["b:random+u:anna", "b:random2+u:ben"]
  assert entry["winner"] == w and entry["set"] == 1 and entry["table"] == "T"
  assert [p["kind"] for p in entry["players"]] == ["human", "human", "bot", "bot"]
  assert entry["deals"] and all(d["set_number"] == 1 for d in entry["deals"])
  assert entry["deals"][-1]["need_after"][w] <= 0
  # The second set is logged too, with the same match id.
  _play_set(t, random.Random(4))
  first, second = db.sets()
  assert second["set"] == 2 and second["match"] == first["match"]
  assert all(d["set_number"] == 2 for d in second["deals"])


def test_guests_seat_changes_and_same_pairs_are_not_rated():
  db = db_lib.Db()
  db.register("Anna", "secret")
  # A guest at the table.
  t = _table(db)
  guest = t.sit(0, "Cleo", creator=True)
  for s in (1, 2, 3):
    t.set_bot(guest, s, "random" if s % 2 else "random2")
  assert t.pair_ratings() == [None, None]
  t.start(guest)
  r = _play_set(t, random.Random(1))
  assert not r["rated"] and r["unrated"] == table_lib.UNRATED_GUEST
  # Someone else sits in during the set.
  t = _table(db)
  anna = t.sit(0, "Anna", creator=True, user="Anna")
  t.set_bot(anna, 1, "random")
  t.set_bot(anna, 2, "random2")
  t.set_bot(anna, 3, "random")
  t.start(anna)
  t.set_bot(anna, 2, "random")  # the creator swaps a bot mid-set
  r = _play_set(t, random.Random(2))
  assert r["unrated"] == table_lib.UNRATED_SEATS
  # The same pair on both sides.
  t = _table(db)
  anna = t.sit(0, "Anna", creator=True, user="Anna")
  for s in range(4):
    t.set_bot(anna, s, "random")
  t.start(anna)
  r = _play_set(t, random.Random(5))
  assert r["unrated"] == table_lib.UNRATED_SAME_PAIR
  assert db.standings() == []
  assert [e["unrated"] for e in db.sets()] == ["guest", "seats changed", "same pair"]


def test_seats_for_users_and_guests():
  db = db_lib.Db()
  db.register("Anna", "secret")
  t = _table(db)
  t.sit(0, "Anna", creator=True, user="Anna")
  with pytest.raises(table_lib.TableError, match="already have a seat"):
    t.sit(1, "Anna", user="Anna")
  with pytest.raises(table_lib.TableError, match="belongs to an account"):
    t.sit(1, "anna")
  t.sit(1, "Cleo")
  seats = t.snapshot(None)["seats"]
  assert [s["account"] for s in seats[:2]] == [True, False]


# -- the API -----------------------------------------------------------------


@pytest.fixture
def client():
  with testclient.TestClient(app_lib.create_app(FAST, _bots())) as c:
    yield c


def test_the_rate_limit_counts_per_address_in_a_minute():
  now = [0.0]
  limit = app_lib.RateLimit(2, clock=lambda: now[0])
  assert limit.allow("a") and limit.allow("a") and not limit.allow("a")
  assert limit.allow("b")
  now[0] = 59.0
  assert not limit.allow("a")
  now[0] = 61.0
  assert limit.allow("a")
  assert all(app_lib.RateLimit(0).allow("a") for _ in range(100))


def test_login_and_register_are_rate_limited():
  settings = dataclasses.replace(FAST, login_rate=3)
  with testclient.TestClient(app_lib.create_app(settings, _bots())) as c:
    anna = {"username": "Anna", "password": "secret"}
    assert c.post("/api/accounts", json=anna).status_code == 200
    assert c.post("/api/login", json=dict(anna, password="nope")).status_code == 400
    assert c.post("/api/login", json=anna).status_code == 200
    r = c.post("/api/login", json=anna)
    assert r.status_code == 429 and r.json()["detail"] == app_lib.TOO_MANY_ATTEMPTS
    assert c.post("/api/accounts", json={"username": "Ben", "password": "secret"}).status_code == 429
    assert c.get("/api/me", headers={}).status_code == 401  # other routes aren't limited


def test_account_api(client):
  r = client.post("/api/accounts", json={"username": "Anna", "password": "secret"})
  assert r.status_code == 200 and r.json()["username"] == "Anna"
  key = r.json()["key"]
  assert client.post("/api/accounts", json={"username": "anna", "password": "secret"}).status_code == 400
  assert client.post("/api/login", json={"username": "Anna", "password": "nope"}).status_code == 400
  key2 = client.post("/api/login", json={"username": "ANNA", "password": "secret"}).json()["key"]
  assert client.get("/api/me", headers={"X-User-Key": key}).json() == {"username": "Anna"}
  assert client.get("/api/me").status_code == 401
  assert client.post("/api/logout", headers={"X-User-Key": key}).status_code == 200
  assert client.get("/api/me", headers={"X-User-Key": key}).status_code == 401
  # A user sits down by key, under their username.
  r = client.post("/api/tables", json={"name": "T", "seat": 0}, headers={"X-User-Key": key2})
  assert r.status_code == 200, r.text
  tid = r.json()["id"]
  seat = client.get("/api/tables").json()[0]["seats"][0]
  assert seat["name"] == "Anna" and seat["account"]
  # A stale key is refused; a guest may not use the name.
  assert client.post(f"/api/tables/{tid}/seats/1", json={"player": "Ben"},
                     headers={"X-User-Key": key}).status_code == 401
  r = client.post(f"/api/tables/{tid}/seats/1", json={"player": "anna"})
  assert r.status_code == 400 and "belongs to an account" in r.text
  assert client.post(f"/api/tables/{tid}/seats/1", json={},
                     headers={"X-User-Key": key2}).status_code == 400


def test_a_bots_only_match_is_rated_and_listed(client):
  r = client.post("/api/tables", json={"name": "Bots", "player": "Cleo", "seat": 0})
  tid, cleo = r.json()["id"], r.json()["token"]
  for seat in range(4):
    bot = "random" if seat % 2 == 0 else "random2"
    assert client.put(f"/api/tables/{tid}/seats/{seat}/bot", json={"bot": bot},
                      headers={"X-Seat-Token": cleo}).status_code == 200
  assert client.get("/api/tables").json()[0]["ratings"] == [600, 600]
  assert client.post(f"/api/tables/{tid}/start", headers={"X-Seat-Token": cleo}).status_code == 200
  deadline = time.time() + 120
  while time.time() < deadline:
    t = client.get("/api/tables").json()[0]
    if t["phase"] == "match_over":
      break
    time.sleep(0.05)
  assert t["phase"] == "match_over", t
  standings = client.get("/api/ratings").json()
  assert {p["key"] for p in standings} == {"b:random+b:random", "b:random2+b:random2"}
  played = sum(t["sets"])
  for p in standings:
    assert p["won"] + p["lost"] == played
  assert sum(p["rating"] for p in standings) in (1199, 1200, 1201)
  assert t["ratings"] == [
      next(p["rating"] for p in standings if p["key"] == k)
      for k in ("b:random+b:random", "b:random2+b:random2")
  ]
  with client.websocket_connect(f"/ws/tables/{tid}") as ws:
    snap = ws.receive_json()
  rating = snap["lastResult"]["rating"]
  assert rating["rated"] and rating["after"] == t["ratings"]
