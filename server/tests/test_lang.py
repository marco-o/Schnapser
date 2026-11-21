"""A table's language: chosen when it is started, Italian by default."""

from fastapi import testclient
import pytest

from schnaps_web import app as app_lib
from schnaps_web import bots as bots_lib
from schnaps_web import config as config_lib
from schnaps_web import table as table_lib

FAST = config_lib.Settings(bot_delay=0.0, deal_pause=0.0, client_dir="/nonexistent")


@pytest.fixture
def client():
  bots = {"random": bots_lib.RandomBot(seed=1)}
  with testclient.TestClient(app_lib.create_app(FAST, bots)) as c:
    yield c


def _create(client, **extra):
  return client.post(
      "/api/tables", json={"name": "Stammtisch", "player": "Anna", "seat": 0, **extra}
  )


def test_italian_by_default(client):
  r = _create(client)
  assert r.status_code == 200, r.text
  assert client.get("/api/tables").json()[0]["lang"] == "it"


@pytest.mark.parametrize("lang", table_lib.LANGS)
def test_every_language_reaches_lobby_and_table(client, lang):
  r = _create(client, lang=lang)
  assert r.status_code == 200, r.text
  tid, token = r.json()["id"], r.json()["token"]
  assert client.get("/api/tables").json()[0]["lang"] == lang
  # Players and spectators see the table's language.
  with client.websocket_connect(f"/ws/tables/{tid}?token={token}") as ws:
    assert ws.receive_json()["lang"] == lang
  with client.websocket_connect(f"/ws/tables/{tid}") as ws:
    assert ws.receive_json()["lang"] == lang


def test_unknown_language_refused(client):
  r = _create(client, lang="fr")
  assert r.status_code == 400
  assert r.json()["detail"] == "unknown language 'fr'"
  assert client.get("/api/tables").json() == []


def test_watch_app_shows_the_language(client):
  tid = _create(client, lang="de").json()["id"]
  watch = app_lib.create_watch_app(client.app.state.lobby, FAST)
  with testclient.TestClient(watch) as w:
    assert w.get("/api/tables").json()[0]["lang"] == "de"
    with w.websocket_connect(f"/ws/tables/{tid}") as ws:
      snap = ws.receive_json()
      assert snap["lang"] == "de" and snap["reveal"]
