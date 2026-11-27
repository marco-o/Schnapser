"""The admin account, its database download / upload (db.py, app.py) and
the set_admin command (tools/set_admin.py)."""

import io
import sqlite3

from fastapi import testclient
import pytest

from schnaps_web import app as app_lib
from schnaps_web import bots as bots_lib
from schnaps_web import config as config_lib
from schnaps_web import db as db_lib
from schnaps_web.tools import set_admin

SET = {"pairs": ["b:basic+u:anna", "b:large+b:large"], "winner": 0,
       "deals": [{"number": 1}]}


PASSWORD = "admin-secret"


def _settings(tmp_path):
  return config_lib.Settings(
      bot_delay=0.0, deal_pause=0.0, client_dir="/nonexistent",
      db_dir=str(tmp_path),
  )


def _bots():
  return {"random": bots_lib.RandomBot(seed=1)}


def test_nobody_registers_admin_from_the_site():
  db = db_lib.Db()
  for name in ("admin", "Admin", " ADMIN "):
    with pytest.raises(db_lib.AccountError):
      db.register(name, "whatever")


def test_setting_the_admin_password():
  db = db_lib.Db()
  assert not db.is_registered("admin")
  with pytest.raises(db_lib.AccountError):
    db.set_admin_password("short")
  assert db.set_admin_password("first-pass-1") is True  # made
  _, key = db.login("admin", "first-pass-1")
  assert db.user_of_key(key) == "admin"
  assert db.set_admin_password("first-pass-1") is False  # same: devices stay
  assert db.user_of_key(key) == "admin"
  db.set_admin_password("second-pass-2")  # changed: devices forgotten
  assert db.user_of_key(key) is None
  with pytest.raises(db_lib.AccountError):
    db.login("admin", "first-pass-1")
  assert db.login("admin", "second-pass-2")[0] == "admin"


def test_the_set_admin_command(tmp_path, monkeypatch, capsys):
  monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
  assert set_admin.main(["--db-dir", str(tmp_path), "--stdin"]) == 0
  assert "Made the admin account" in capsys.readouterr().out
  assert db_lib.Db(str(tmp_path)).login("admin", PASSWORD)[0] == "admin"
  # Asked twice; different answers change nothing.
  answers = iter(["new-password-1", "new-password-2"])
  monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
  assert set_admin.main(["--db-dir", str(tmp_path)]) == 1
  assert db_lib.Db(str(tmp_path)).login("admin", PASSWORD)[0] == "admin"
  answers = iter(["new-password-1", "new-password-1"])
  assert set_admin.main(["--db-dir", str(tmp_path)]) == 0
  assert "Admin password set" in capsys.readouterr().out
  assert db_lib.Db(str(tmp_path)).login("admin", "new-password-1")[0] == "admin"
  # Too short: refused.
  monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
  assert set_admin.main(["--db-dir", str(tmp_path), "--stdin"]) == 1


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


def test_an_upload_keeps_the_admin_as_it_was(tmp_path):
  db = db_lib.Db(str(tmp_path / "site"))
  db.set_admin_password(PASSWORD)
  _, key = db.login("admin", PASSWORD)
  # A file with no admin, and one whose admin has another password.
  without_admin = db_lib.Db(str(tmp_path / "old")).export_file()
  other = db_lib.Db(str(tmp_path / "other"))
  other.set_admin_password("someone-elses")
  for data in (without_admin, other.export_file()):
    db.replace_file(data)
    assert db.user_of_key(key) == "admin"
    assert db.login("admin", PASSWORD)[0] == "admin"
    with pytest.raises(db_lib.AccountError):
      db.login("admin", "someone-elses")
  # With no admin before, the file's own admin comes in.
  fresh = db_lib.Db(str(tmp_path / "fresh"))
  fresh.replace_file(other.export_file())
  assert fresh.login("admin", "someone-elses")[0] == "admin"


def test_the_admin_api(tmp_path):
  db_lib.Db(str(tmp_path)).set_admin_password(PASSWORD)
  with testclient.TestClient(app_lib.create_app(_settings(tmp_path), _bots())) as c:
    admin = c.post("/api/login", json={"username": "admin", "password": PASSWORD})
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
  db_lib.Db(str(tmp_path)).set_admin_password(PASSWORD)
  with testclient.TestClient(app_lib.create_app(_settings(tmp_path), _bots())) as c:
    key = c.post("/api/login", json={"username": "admin", "password": PASSWORD}).json()["key"]
    r = c.put("/api/admin/database", headers={"X-User-Key": key}, content=b"x" * 5000)
    assert r.status_code == 413


def test_the_site_makes_no_admin_by_itself(tmp_path):
  with testclient.TestClient(app_lib.create_app(_settings(tmp_path), _bots())) as c:
    r = c.post("/api/login", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 400
