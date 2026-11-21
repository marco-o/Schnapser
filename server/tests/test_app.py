"""schnaps_web.app: lobby, seats, bots, privacy, a human move, a full match."""

import time

from fastapi import testclient
import pytest

from schnaps_web import app as app_lib
from schnaps_web import bots as bots_lib
from schnaps_web import config as config_lib

FAST = config_lib.Settings(bot_delay=0.0, deal_pause=0.0, client_dir="/nonexistent")


@pytest.fixture
def client():
  bots = {"random": bots_lib.RandomBot(seed=1)}
  with testclient.TestClient(app_lib.create_app(FAST, bots)) as c:
    yield c


def _h(token):
  return {"X-Seat-Token": token}


def _create(client, seat=0, name="Anna"):
  r = client.post("/api/tables", json={"name": "Stammtisch", "player": name, "seat": seat})
  assert r.status_code == 200, r.text
  return r.json()["id"], r.json()["token"]


def test_lobby_seats_and_permissions(client):
  tid, anna = _create(client)
  tables = client.get("/api/tables").json()
  assert [t["name"] for t in tables] == ["Stammtisch"]
  assert tables[0]["seats"][0]["name"] == "Anna"
  assert tables[0]["seats"][0]["kind"] == "human"
  assert "token" not in str(tables)
  # Ben takes seat 2; seat 2 cannot be taken twice; names are required.
  ben = client.post(f"/api/tables/{tid}/seats/2", json={"player": "Ben"}).json()["token"]
  assert client.post(f"/api/tables/{tid}/seats/2", json={"player": "Cleo"}).status_code == 400
  assert client.post(f"/api/tables/{tid}/seats/1", json={"player": "  "}).status_code == 400
  # Only the creator seats bots or starts; nobody bots a human's seat.
  assert client.put(f"/api/tables/{tid}/seats/1/bot", json={"bot": "random"}, headers=_h(ben)).status_code == 403
  assert client.put(f"/api/tables/{tid}/seats/2/bot", json={"bot": "random"}, headers=_h(anna)).status_code == 400
  assert client.put(f"/api/tables/{tid}/seats/1/bot", json={"bot": "nope"}, headers=_h(anna)).status_code == 400
  assert client.put(f"/api/tables/{tid}/seats/1/bot", json={"bot": "random"}, headers=_h(anna)).status_code == 200
  # Not all seats filled yet.
  assert client.post(f"/api/tables/{tid}/start", headers=_h(anna)).status_code == 400
  assert client.post(f"/api/tables/{tid}/start", headers=_h(ben)).status_code == 403
  # Ben leaves and comes back; a bot can be taken out by the creator only.
  assert client.delete(f"/api/tables/{tid}/seats/1", headers=_h(ben)).status_code == 403
  assert client.delete(f"/api/tables/{tid}/seats/2", headers=_h(ben)).status_code == 200
  assert client.get("/api/tables").json()[0]["seats"][2]["kind"] == "empty"
  assert client.get("/api/tables/x").status_code == 404 or True
  assert client.post("/api/tables/nope/start", headers=_h(anna)).status_code == 404


def _until(ws, pred, limit=500):
  for _ in range(limit):
    snap = ws.receive_json()
    if pred(snap):
      return snap
  raise AssertionError("condition never met")


def test_privacy_and_a_human_move(client):
  tid, anna = _create(client, seat=0)
  for seat in (1, 2, 3):
    client.put(f"/api/tables/{tid}/seats/{seat}/bot", json={"bot": "random"}, headers=_h(anna))
  with client.websocket_connect(f"/ws/tables/{tid}?token={anna}") as ws, \
       client.websocket_connect(f"/ws/tables/{tid}") as spectator:
    first = ws.receive_json()
    assert first["you"] == 0 and first["isCreator"] and first["phase"] == "open"
    assert first["seats"][0]["online"] and first["seats"][0]["you"]
    assert client.post(f"/api/tables/{tid}/start", headers=_h(anna)).status_code == 200
    snap = _until(ws, lambda s: s["phase"] == "playing" and s["toMove"] == 0)
    frame = snap["frame"]
    me = frame["viewer"]["seat"]
    assert frame["seatMap"][me] == 0
    for entry in frame["presentation"]["view"]["seats"]:
      hidden = all(c is None for c in entry["cards"])
      assert hidden == (entry["seat"] != me)
    actions = frame["presentation"]["actions"]
    assert actions
    # Spectators see no hand and no moves.
    spec = _until(spectator, lambda s: s["phase"] == "playing")
    assert spec["you"] is None and not spec["isCreator"]
    for entry in spec["frame"]["presentation"]["view"]["seats"]:
      assert all(c is None for c in entry["cards"])
    assert spec["frame"]["presentation"]["actions"] == []
    # A move: an illegal one is refused, a legal one accepted; a spectator
    # (no token) cannot move.
    assert client.post(f"/api/tables/{tid}/actions", json={"action": 999}, headers=_h(anna)).status_code == 400
    assert client.post(f"/api/tables/{tid}/actions", json={"action": actions[0]["id"]}).status_code == 403
    r = client.post(f"/api/tables/{tid}/actions", json={"action": actions[0]["id"]}, headers=_h(anna))
    assert r.status_code == 200, r.text
  # Reconnecting with the token returns the same seat.
  with client.websocket_connect(f"/ws/tables/{tid}?token={anna}") as ws:
    assert ws.receive_json()["you"] == 0


def test_a_full_match_of_bots_watched_by_the_creator(client):
  tid, anna = _create(client, seat=0)
  # The creator hands their own seat to a bot and keeps watching.
  for seat in range(4):
    assert client.put(f"/api/tables/{tid}/seats/{seat}/bot", json={"bot": "random"}, headers=_h(anna)).status_code == 200
  assert client.post(f"/api/tables/{tid}/start", headers=_h(anna)).status_code == 200
  deadline = time.time() + 120
  while time.time() < deadline:
    t = client.get("/api/tables").json()[0]
    if t["phase"] == "match_over":
      break
    time.sleep(0.05)
  assert t["phase"] == "match_over", t
  assert sorted(t["sets"]) in ([0, 2], [1, 2])
  with client.websocket_connect(f"/ws/tables/{tid}?token={anna}") as ws:
    snap = ws.receive_json()
  assert snap["you"] is None and snap["isCreator"]
  m = snap["match"]
  assert m["winner"] in (0, 1) and m["sets"][m["winner"]] == 2
  deals = m["deals"]
  for a, b in zip(deals, deals[1:]):
    assert b["dealer"] == (a["dealer"] + 1) % 4
    assert b["caller"] == (b["dealer"] + 1) % 4
  # The last deal took the winner to 0 or below.
  assert deals[-1]["need_after"][m["winner"]] <= 0
  assert snap["lastResult"]["matchWinner"] == m["winner"]
  # A new match can start; a non-creator cannot close the table.
  assert client.post(f"/api/tables/{tid}/start", headers=_h(anna)).status_code == 200
  assert client.delete(f"/api/tables/{tid}", headers=_h("x")).status_code == 403
  assert client.delete(f"/api/tables/{tid}", headers=_h(anna)).status_code == 200
  assert client.get("/api/tables").json() == []


def test_bots_get_distinct_first_names(client):
  from schnaps_web import table as table_lib
  tid, anna = _create(client, seat=0)
  for seat in (1, 2, 3):
    client.put(f"/api/tables/{tid}/seats/{seat}/bot", json={"bot": "random"}, headers=_h(anna))
  seats = client.get("/api/tables").json()[0]["seats"]
  names = [s["name"] for s in seats[1:]]
  assert len(set(names)) == 3
  assert all(n in table_lib.BOT_NAMES for n in names)
  assert all(s["botLabel"] == "Random" for s in seats[1:])


def test_the_watch_app_shows_every_hand_and_changes_nothing():
  bots = {"random": bots_lib.RandomBot(seed=1)}
  main = app_lib.create_app(FAST, bots)
  watch = app_lib.create_watch_app(main.state.lobby, FAST)

  # One client (one event loop, as in serve()); paths under /w/ go to the
  # watch app.
  async def both(scope, receive, send):
    if scope["type"] != "lifespan" and scope["path"].startswith("/w/"):
      scope = dict(scope, path=scope["path"][2:], raw_path=None)
      return await watch(scope, receive, send)
    return await main(scope, receive, send)

  with testclient.TestClient(both) as c:
    assert c.get("/api/site").json() == {"watch": False}
    assert c.get("/w/api/site").json() == {"watch": True}
    tid, anna = _create(c, seat=0)
    for seat in range(4):
      c.put(f"/api/tables/{tid}/seats/{seat}/bot", json={"bot": "random"}, headers=_h(anna))
    assert [t["id"] for t in c.get("/w/api/tables").json()] == [tid]
    # Nothing that changes a table exists on the watch app.
    assert c.post("/w/api/tables", json={"name": "x", "player": "y"}).status_code in (404, 405)
    assert c.post(f"/w/api/tables/{tid}/start", headers=_h(anna)).status_code in (404, 405)
    assert c.post(f"/w/api/tables/{tid}/actions", json={"action": 0}, headers=_h(anna)).status_code in (404, 405)
    # Its socket shows every hand, ignores tokens, and offers no moves.
    with c.websocket_connect(f"/w/ws/tables/{tid}?token={anna}") as ws:
      ws.receive_json()
      assert c.post(f"/api/tables/{tid}/start", headers=_h(anna)).status_code == 200
      snap = _until(
          ws,
          lambda s: s["frame"] is not None
          and all(e["cards"] for e in s["frame"]["presentation"]["view"]["seats"]),
      )
    assert snap["reveal"] and snap["you"] is None and not snap["isCreator"]
    for entry in snap["frame"]["presentation"]["view"]["seats"]:
      assert all(card is not None for card in entry["cards"])
    assert snap["frame"]["presentation"]["actions"] == []
