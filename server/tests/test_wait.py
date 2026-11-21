"""Table.wait: a seated player holds the next deal back with "Wait"."""

import time

from fastapi import testclient

from schnaps_web import app as app_lib
from schnaps_web import bots as bots_lib
from schnaps_web import config as config_lib

# A short pause, so a test can press Wait before the next deal comes.
SETTINGS = config_lib.Settings(bot_delay=0.0, deal_pause=0.5, client_dir="/nonexistent")


def _h(token):
  return {"X-Seat-Token": token}


def _table(client):
  """Anna in seat 0 with three bots, the match started: (id, token)."""
  r = client.post("/api/tables", json={"name": "T", "player": "Anna", "seat": 0})
  tid, anna = r.json()["id"], r.json()["token"]
  for seat in (1, 2, 3):
    client.put(f"/api/tables/{tid}/seats/{seat}/bot", json={"bot": "random"}, headers=_h(anna))
  assert client.post(f"/api/tables/{tid}/start", headers=_h(anna)).status_code == 200
  return tid, anna


def _to_deal_over(client, tid, anna, ws, timeout=60):
  """Anna plays her first legal move whenever asked, until a deal ends."""
  deadline = time.time() + timeout
  while time.time() < deadline:
    snap = ws.receive_json()
    if snap["phase"] == "deal_over":
      return snap
    actions = (snap["frame"] or {}).get("presentation", {}).get("actions")
    if snap["phase"] == "playing" and actions:
      client.post(
          f"/api/tables/{tid}/actions", json={"action": actions[0]["id"]}, headers=_h(anna)
      )
  raise AssertionError("no deal ended")


def _phase(client):
  return client.get("/api/tables").json()[0]["phase"]


def _wait(client, tid, token, on):
  headers = _h(token) if token else {}
  return client.post(f"/api/tables/{tid}/wait", json={"on": on}, headers=headers)


def test_wait_holds_the_next_deal_until_released():
  bots = {"random": bots_lib.RandomBot(seed=5)}
  with testclient.TestClient(app_lib.create_app(SETTINGS, bots)) as client:
    tid, anna = _table(client)
    # Not during a deal (it waits for Anna's move), not without a seat,
    # only true or false.
    r = _wait(client, tid, anna, True)
    assert r.status_code == 400 and "no deal has just ended" in r.text
    with client.websocket_connect(f"/ws/tables/{tid}?token={anna}") as ws:
      snap = _to_deal_over(client, tid, anna, ws)
      assert snap["waiting"] == []
      assert _wait(client, tid, None, True).status_code == 403
      assert _wait(client, tid, anna, "yes").status_code == 400
      r = _wait(client, tid, anna, True)
      if r.status_code == 400:  # the pause ran out first: try the next deal
        snap = _to_deal_over(client, tid, anna, ws)
        r = _wait(client, tid, anna, True)
      assert r.status_code == 200, r.text
      deals = len(snap["match"]["deals"])
      # Well past the pause, the table still waits for Anna.
      time.sleep(SETTINGS.deal_pause * 4)
      assert _phase(client) == "deal_over"
      with client.websocket_connect(f"/ws/tables/{tid}?token={anna}") as ws2:
        held = ws2.receive_json()
      assert held["waiting"] == [0] and len(held["match"]["deals"]) == deals
      # Letting go after the pause starts the next deal at once.
      assert _wait(client, tid, anna, False).status_code == 200
      deadline = time.time() + 5
      while time.time() < deadline and _phase(client) == "deal_over":
        time.sleep(0.02)
      # The next deal runs (and waits for Anna's move); Wait is refused.
      assert _phase(client) == "playing"
      assert _wait(client, tid, anna, True).status_code == 400


def test_an_offline_players_wait_does_not_hold_the_table():
  bots = {"random": bots_lib.RandomBot(seed=6)}
  with testclient.TestClient(app_lib.create_app(SETTINGS, bots)) as client:
    tid, anna = _table(client)
    with client.websocket_connect(f"/ws/tables/{tid}?token={anna}") as ws:
      _to_deal_over(client, tid, anna, ws)
      r = _wait(client, tid, anna, True)
      while r.status_code == 400:  # the pause ran out first
        _to_deal_over(client, tid, anna, ws)
        r = _wait(client, tid, anna, True)
      time.sleep(SETTINGS.deal_pause * 2)
      assert _phase(client) == "deal_over"
    # Anna's connection is gone: her Wait no longer counts.
    deadline = time.time() + 5
    while time.time() < deadline and _phase(client) == "deal_over":
      time.sleep(0.02)
    assert _phase(client) != "deal_over"
