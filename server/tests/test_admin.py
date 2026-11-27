"""The admin account and its database download / upload (db.py, app.py)."""

import dataclasses
import sqlite3

from fastapi import testclient
import pytest

from schnaps_web import app as app_lib
from schnaps_web import bots as bots_lib
from schnaps_web import config as config_lib
from schnaps_web import db as db_lib

SET = {"pairs": ["b:basic+u:anna", "b:large+b:large"], "winner": 0,
       "deals": [{"number": 1}]}


def _settings(tmp_path, password="admin-secret"):
  return config_lib.Settings(
      bot_delay=0.0, deal_pause=0.0, client_dir="/nonexistent",
      db_dir=str(tmp_path), admin_password=password,
  )


def _bots():
  return {"random": bots_lib.RandomBot(seed=1)}


def test_nobody_registers_admin_from_the_site():
  db = db_lib.Db()
  for name in ("admin", "Admin", " ADMIN "):
    with pytest.raises(db_lib.AccountError):
      db.register(name, "whatever")


def test_the_admin_account_comes_from_the_setting():
  db = db_lib.Db()
  db.ensure_admin("")  # no password: no admin
  assert not db.is_registered("admin")
  db.ensure_admin("first-pass")
  _, key = db.login("admin", "first-pass")
  assert db.user_of_key(key) == "admin"
  db.ensure_admin("first-pass")  # unchanged: the devices stay logged in
  assert db.user_of_key(key) == "admin"
  db.ensure_admin("second-pass")  # changed: new password, devices forgotten
  assert db.user_of_key(key) is None
  with pytest.raises(db_lib.AccountError):
    db.login("admin", "first-pass")
  assert db.login("admin", "second-pass")[0] == "admin"
  assert repr(config_lib.Settings(admin_password="x")).count("'x'") == 0


def test_export_and_replace_round_trip(tmp_path):
  db = db_lib.Db(str(tmp_path / "a"))
  db.register("Anna", "secret")
  db.record_set(SET)
  data = db.export_file()
  assert data.startswith(db_lib.SQLITE_HEADER)

  other = db_lib.Db(str(tmp_path / "b"))
  other.register("Bruno", "secret")
  counts = other.replace_file(data)
  assert (counts["users"], counts["pairs"], counts["sets"]) == (1, 2, 1)
  assert other.is_registered("Anna") and not other.is_registered("Bruno")
  assert other.rating("b:basic+u:anna") == 616.0
  # The database replaced is kept in backups/, Bruno and all.
  (backup,) = (tmp_path / "b" / "backups").iterdir()
  assert counts["backup"] == str(backup)
  kept = sqlite3.connect(backup)
  assert kept.execute("SELECT name FROM users").fetchall() == [("Bruno",)]
  kept.close()
  # And it survives a restart.
  other.close()
  assert db_lib.Db(str(tmp_path / "b")).is_registered("Anna")


def test_replace_refuses_files_that_are_not_this_sites(tmp_path):
  db = db_lib.Db(str(tmp_path))
  db.register("Anna", "secret")
  foreign = tmp_path / "foreign.db"
  conn = sqlite3.connect(foreign)
  conn.execute("CREATE TABLE things (x)")
  conn.commit()
  conn.close()
  newer = db_lib.Db(str(tmp_path / "newer"))
  newer._conn.execute("PRAGMA user_version = 99")  # pylint: disable=protected-access
  newer._conn.commit()  # pylint: disable=protected-access
  for bad in (b"not a database", b"SQLite format 3\x00" + b"\x00" * 200,
              foreign.read_bytes(), newer.export_file()):
    with pytest.raises(db_lib.DatabaseFileError):
      db.replace_file(bad)
  assert db.is_registered("Anna")
  assert not (tmp_path / "backups").exists()


def test_an_uploaded_file_cannot_lock_the_admin_out(tmp_path):
  db = db_lib.Db(str(tmp_path / "site"))
  db.ensure_admin("admin-secret")
  without_admin = db_lib.Db(str(tmp_path / "old")).export_file()
  db.replace_file(without_admin, "admin-secret")
  assert db.login("admin", "admin-secret")[0] == "admin"


def test_the_admin_api(tmp_path):
  with testclient.TestClient(app_lib.create_app(_settings(tmp_path), _bots())) as c:
    admin = c.post("/api/login", json={"username": "admin", "password": "admin-secret"})
    assert admin.status_code == 200
    akey = {"X-User-Key": admin.json()["key"]}
    anna = c.post("/api/accounts", json={"username": "Anna", "password": "secret"})
    ukey = {"X-User-Key": anna.json()["key"]}
    assert c.post("/api/accounts", json={"username": "admin", "password": "x1234"}).status_code == 400

    # Only the admin.
    assert c.get("/api/admin/database").status_code == 401
    assert c.get("/api/admin/database", headers=ukey).status_code == 403
    assert c.put("/api/admin/database", headers=ukey, content=b"x").status_code == 403

    got = c.get("/api/admin/database", headers=akey)
    assert got.status_code == 200
    assert got.headers["content-type"] == "application/vnd.sqlite3"
    assert 'filename="schnaps-' in got.headers["content-disposition"]
    saved = got.content
    assert saved.startswith(db_lib.SQLITE_HEADER)

    # Bruno registers after the download; loading the download back drops him.
    c.post("/api/accounts", json={"username": "Bruno", "password": "secret"})
    bad = c.put("/api/admin/database", headers=akey, content=b"nonsense")
    assert bad.status_code == 400
    up = c.put("/api/admin/database", headers=akey, content=saved)
    assert up.status_code == 200, up.text
    assert up.json() == {"users": 2, "pairs": 0, "sets": 0}
    assert c.get("/api/me", headers=ukey).json() == {"username": "Anna"}
    assert c.post("/api/login", json={"username": "Bruno", "password": "secret"}).status_code == 400
    assert c.get("/api/me", headers=akey).status_code == 200
  assert len(list((tmp_path / "backups").iterdir())) == 1


def test_the_upload_has_a_size_limit(tmp_path, monkeypatch):
  monkeypatch.setattr(app_lib, "MAX_DATABASE_UPLOAD", 1000)
  with testclient.TestClient(app_lib.create_app(_settings(tmp_path), _bots())) as c:
    key = c.post("/api/login", json={"username": "admin", "password": "admin-secret"}).json()["key"]
    r = c.put("/api/admin/database", headers={"X-User-Key": key}, content=b"x" * 5000)
    assert r.status_code == 413


def test_no_admin_without_the_setting(tmp_path):
  settings = dataclasses.replace(_settings(tmp_path), admin_password="")
  with testclient.TestClient(app_lib.create_app(settings, _bots())) as c:
    r = c.post("/api/login", json={"username": "admin", "password": "admin-secret"})
    assert r.status_code == 400
