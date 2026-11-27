"""The web app: the lobby and table API, a WebSocket per table, the client.

REST (JSON; a seat token goes in the X-Seat-Token header, a logged-in
device's key in X-User-Key):

  POST   /api/accounts                      {username, password} -> {username, key}
  POST   /api/login                         {username, password} -> {username, key}
         (both: 429 after settings.login_rate requests from one address
         in 60 seconds, when login_rate is set)
  GET    /api/me                            (X-User-Key) -> {username}
  POST   /api/logout                        (X-User-Key) forget this device
  GET    /api/admin/database                (X-User-Key of "admin") the whole
         database, an SQLite file to save (db.export_file)
  PUT    /api/admin/database                (X-User-Key of "admin", body: an
         SQLite file, at most MAX_DATABASE_UPLOAD bytes) replace the whole
         database; the old one goes to backups/ -> {users, pairs, sets}
         (400: not a database of this site; 403: not the admin)
  GET    /api/ratings                       the rated pairs, best first
  GET    /api/bots                          the bot catalog
  GET    /api/tables                        the lobby's tables
  POST   /api/tables                        {name, player, seat} -> {id, token}
  POST   /api/tables/{id}/seats/{n}         {player} -> {token}: take a seat

Creating a table or taking a seat with X-User-Key sits down as that user
(no "player" needed); without it, as a guest with the nickname "player".
A key the database does not know is refused (401), so the client can
forget it.
  PUT    /api/tables/{id}/seats/{n}/bot     {bot}: the creator seats a bot
  DELETE /api/tables/{id}/seats/{n}         empty a seat (own, or a bot)
  POST   /api/tables/{id}/start             the creator starts a match
  POST   /api/tables/{id}/actions           {action}: play a move
  POST   /api/tables/{id}/throw             {kind}: "resign"
  POST   /api/tables/{id}/show              show your hand to the opponents
  POST   /api/tables/{id}/wait              {on}: hold the next deal back
  DELETE /api/tables/{id}                   the creator closes the table

WebSocket /ws/tables/{id}?token=...: the table's snapshot (table.snapshot)
on connect and after every change, as seen by that token (no token: a
spectator).

GET /api/site says which app this is ({"watch": false}).

The watch app (create_watch_app, settings.watch_port, default 8001) shares
the lobby but is read-only: GET /api/site ({"watch": true}), GET
/api/tables, GET /api/ratings and the WebSocket, which shows every hand to
everyone.

Everything else serves the built client (client/dist), with index.html for
the client's own routes.

  python -m schnaps_web.app        # both ports (serve)
"""

import asyncio
import os
import time
from typing import Any, Callable, Optional

import fastapi
from fastapi import responses
from fastapi import staticfiles

from schnaps_web import bots as bots_lib
from schnaps_web import config as config_lib
from schnaps_web import db as db_lib
from schnaps_web import lobby as lobby_lib
from schnaps_web import table as table_lib

#: The 429 message (the client translates it: errTooManyAttempts).
TOO_MANY_ATTEMPTS = "too many attempts; try again in a minute"

#: The 403 message of the admin calls (the client translates it: errNotAdmin).
ONLY_ADMIN = "only the admin may do this"

#: The largest database file the admin may upload (deploy/Caddyfile allows
#: the same on that path).
MAX_DATABASE_UPLOAD = 100 * 1024 * 1024


class RateLimit:
  """At most `per_minute` hits per client address in any 60 seconds.

  Args:
    per_minute: the limit; 0 or less: no limit.
    clock: seconds, monotonic (tests pass their own).
  """

  WINDOW = 60.0
  #: Addresses kept before old ones are dropped (a bound on memory).
  MAX_ADDRESSES = 10_000

  def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic):
    self._limit = per_minute
    self._clock = clock
    self._hits: dict[str, list[float]] = {}

  def allow(self, who: str) -> bool:
    """Counts a hit from `who`; False when it is over the limit."""
    if self._limit <= 0:
      return True
    now = self._clock()
    hits = [t for t in self._hits.get(who, ()) if now - t < self.WINDOW]
    allowed = len(hits) < self._limit
    if allowed:
      hits.append(now)
    self._hits[who] = hits
    if len(self._hits) > self.MAX_ADDRESSES:
      self._hits = {
          k: v for k, v in self._hits.items()
          if v and now - v[-1] < self.WINDOW
      }
    return allowed


def create_app(
    settings: Optional[config_lib.Settings] = None,
    bots: Optional[dict] = None,
) -> fastapi.FastAPI:
  """The app.

  Args:
    settings: the settings (default: config.from_env()).
    bots: the bot catalog (default: bots.make_bots, which loads the Basic
      and, when built, the Large and 2a players, plus the Napoli search bot).

  Returns:
    The FastAPI app.
  """
  settings = settings or config_lib.from_env()
  if bots is None:
    bots = bots_lib.make_bots(
        settings.basic_model_dir,
        settings.large_model_dir,
        settings.mixed_model_dir,
        search_samples=settings.search_samples,
    )
  lobby = lobby_lib.Lobby(bots, settings)
  app = fastapi.FastAPI(title="Schnaps")
  app.state.lobby = lobby

  def table_of(table_id: str) -> table_lib.Table:
    try:
      return lobby.get(table_id)
    except KeyError:
      raise fastapi.HTTPException(404, "no such table") from None

  db = lobby.db

  def guarded(fn, *args, **kwargs):
    try:
      return fn(*args, **kwargs)
    except table_lib.Forbidden as e:
      raise fastapi.HTTPException(403, str(e)) from None
    except (table_lib.TableError, db_lib.AccountError) as e:
      raise fastapi.HTTPException(400, str(e)) from None

  def body_field(body: Any, key: str):
    if not isinstance(body, dict) or key not in body:
      raise fastapi.HTTPException(400, f"missing {key!r}")
    return body[key]

  def user_of(key: Optional[str]) -> Optional[str]:
    """The username of a device key; None without one; 401 if unknown."""
    if not key:
      return None
    user = db.user_of_key(key)
    if user is None:
      raise fastapi.HTTPException(401, "unknown account; log in again")
    return user

  def player_of(body: Any, key: Optional[str]) -> tuple[str, Optional[str]]:
    """(name, username or None): the user of the key, else the nickname."""
    user = user_of(key)
    if user is not None:
      return user, user
    return body_field(body, "player"), None

  @app.get("/api/site")
  async def site():
    return {"watch": False}

  limit = RateLimit(settings.login_rate)

  async def account_call(request: fastapi.Request, fn, body: Any):
    """Rate-limits, then runs a register/login call off the event loop
    (its PBKDF2 hash takes a while; the tables keep going meanwhile)."""
    if not limit.allow(request.client.host if request.client else "?"):
      raise fastapi.HTTPException(429, TOO_MANY_ATTEMPTS)
    username = body_field(body, "username")
    password = body_field(body, "password")
    return await asyncio.to_thread(guarded, fn, username, password)

  @app.post("/api/accounts")
  async def register(request: fastapi.Request, body: dict = fastapi.Body(...)):
    name, key = await account_call(request, db.register, body)
    return {"username": name, "key": key}

  @app.post("/api/login")
  async def login(request: fastapi.Request, body: dict = fastapi.Body(...)):
    name, key = await account_call(request, db.login, body)
    return {"username": name, "key": key}

  @app.get("/api/me")
  async def me(x_user_key: Optional[str] = fastapi.Header(None)):
    user = user_of(x_user_key)
    if user is None:
      raise fastapi.HTTPException(401, "unknown account; log in again")
    return {"username": user}

  @app.post("/api/logout")
  async def logout(x_user_key: Optional[str] = fastapi.Header(None)):
    db.logout(x_user_key)
    return {"ok": True}

  def admin_of(key: Optional[str]) -> str:
    """The admin's username; 401 without a known key, 403 for others."""
    user = user_of(key)
    if user is None:
      raise fastapi.HTTPException(401, "unknown account; log in again")
    if not db.is_admin(user):
      raise fastapi.HTTPException(403, ONLY_ADMIN)
    return user

  @app.get("/api/admin/database")
  async def download_database(x_user_key: Optional[str] = fastapi.Header(None)):
    admin_of(x_user_key)
    data = await asyncio.to_thread(db.export_file)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    return responses.Response(
        data,
        media_type="application/vnd.sqlite3",
        headers={
            "Content-Disposition": f'attachment; filename="schnaps-{stamp}.db"',
            "Cache-Control": "no-store",
        },
    )

  @app.put("/api/admin/database")
  async def upload_database(
      request: fastapi.Request, x_user_key: Optional[str] = fastapi.Header(None)
  ):
    admin_of(x_user_key)
    chunks, size = [], 0
    async for chunk in request.stream():
      size += len(chunk)
      if size > MAX_DATABASE_UPLOAD:
        raise fastapi.HTTPException(413, "the file is too large")
      chunks.append(chunk)
    try:
      counts = await asyncio.to_thread(db.replace_file, b"".join(chunks))
    except db_lib.DatabaseFileError as e:
      raise fastapi.HTTPException(400, str(e)) from None
    print(f"Database replaced by the admin; the old one is in {counts['backup']}",
          flush=True)
    return {k: counts[k] for k in ("users", "pairs", "sets")}

  _add_ratings(app, db)

  @app.get("/api/bots")
  async def list_bots():
    return [{"name": b.name, "label": b.label} for b in bots.values()]

  @app.get("/api/tables")
  async def list_tables():
    return lobby.summaries()

  @app.post("/api/tables")
  async def create_table(
      body: dict = fastapi.Body(...),
      x_user_key: Optional[str] = fastapi.Header(None),
  ):
    player, user = player_of(body, x_user_key)
    table, token = guarded(
        lobby.create,
        body_field(body, "name"),
        player,
        body.get("seat", 0),
        body.get("lang"),
        user,
    )
    return {"id": table.id, "token": token}

  @app.post("/api/tables/{table_id}/seats/{seat}")
  async def take_seat(
      table_id: str,
      seat: int,
      body: dict = fastapi.Body(...),
      x_user_key: Optional[str] = fastapi.Header(None),
  ):
    table = table_of(table_id)
    player, user = player_of(body, x_user_key)
    return {"token": guarded(table.sit, seat, player, user=user)}

  @app.put("/api/tables/{table_id}/seats/{seat}/bot")
  async def seat_bot(
      table_id: str,
      seat: int,
      body: dict = fastapi.Body(...),
      x_seat_token: Optional[str] = fastapi.Header(None),
  ):
    table = table_of(table_id)
    guarded(table.set_bot, x_seat_token, seat, body_field(body, "bot"))
    return {"ok": True}

  @app.delete("/api/tables/{table_id}/seats/{seat}")
  async def empty_seat(
      table_id: str,
      seat: int,
      x_seat_token: Optional[str] = fastapi.Header(None),
  ):
    guarded(table_of(table_id).clear_seat, x_seat_token, seat)
    return {"ok": True}

  @app.post("/api/tables/{table_id}/start")
  async def start(table_id: str, x_seat_token: Optional[str] = fastapi.Header(None)):
    guarded(table_of(table_id).start, x_seat_token)
    return {"ok": True}

  @app.post("/api/tables/{table_id}/actions")
  async def act(
      table_id: str,
      body: dict = fastapi.Body(...),
      x_seat_token: Optional[str] = fastapi.Header(None),
  ):
    guarded(table_of(table_id).act, x_seat_token, body_field(body, "action"))
    return {"ok": True}

  @app.post("/api/tables/{table_id}/throw")
  async def throw(
      table_id: str,
      body: dict = fastapi.Body(...),
      x_seat_token: Optional[str] = fastapi.Header(None),
  ):
    guarded(table_of(table_id).throw, x_seat_token, body_field(body, "kind"))
    return {"ok": True}

  @app.post("/api/tables/{table_id}/show")
  async def show(table_id: str, x_seat_token: Optional[str] = fastapi.Header(None)):
    guarded(table_of(table_id).show, x_seat_token)
    return {"ok": True}

  @app.post("/api/tables/{table_id}/wait")
  async def wait(
      table_id: str,
      body: dict = fastapi.Body(...),
      x_seat_token: Optional[str] = fastapi.Header(None),
  ):
    guarded(table_of(table_id).wait, x_seat_token, body_field(body, "on"))
    return {"ok": True}

  @app.delete("/api/tables/{table_id}")
  async def close(table_id: str, x_seat_token: Optional[str] = fastapi.Header(None)):
    guarded(table_of(table_id).close, x_seat_token)
    return {"ok": True}

  _add_socket(app, lobby, reveal=False)
  _add_client(app, settings)
  return app


def create_watch_app(
    lobby: lobby_lib.Lobby, settings: config_lib.Settings
) -> fastapi.FastAPI:
  """The all-cards watch app (settings.watch_port): read-only, every hand.

  It serves the same client and lobby list, and each table's WebSocket
  with every hand shown; it has no route that changes anything.
  """
  app = fastapi.FastAPI(title="Schnaps (watch)")
  app.state.lobby = lobby

  @app.get("/api/site")
  async def site():
    return {"watch": True}

  @app.get("/api/tables")
  async def list_tables():
    return lobby.summaries()

  _add_ratings(app, lobby.db)
  _add_socket(app, lobby, reveal=True)
  _add_client(app, settings)
  return app


def _add_ratings(app: fastapi.FastAPI, db: db_lib.Db) -> None:
  """GET /api/ratings: every rated pair, best first (db.Db.standings)."""

  @app.get("/api/ratings")
  async def ratings():
    return db.standings()


def _add_socket(app: fastapi.FastAPI, lobby: lobby_lib.Lobby, reveal: bool) -> None:
  """WebSocket /ws/tables/{id}: the table's snapshots (`reveal`: all hands)."""

  @app.websocket("/ws/tables/{table_id}")
  async def watch(websocket: fastapi.WebSocket, table_id: str):
    try:
      table = lobby.get(table_id)
    except KeyError:
      await websocket.close(code=4404)
      return
    await websocket.accept()
    token = None if reveal else (websocket.query_params.get("token") or None)
    listener = table_lib.Listener(token, websocket.send_json, reveal)
    await table.attach(listener)
    try:
      while True:
        await websocket.receive_text()  # keep-alive pings; nothing else
    except fastapi.WebSocketDisconnect:
      pass
    finally:
      table.detach(listener)


def _add_client(app: fastapi.FastAPI, settings: config_lib.Settings) -> None:
  """The client: built files, and index.html for its own routes."""
  index = os.path.join(settings.client_dir, "index.html")
  assets = os.path.join(settings.client_dir, "assets")
  if os.path.isdir(assets):
    app.mount("/assets", staticfiles.StaticFiles(directory=assets), "assets")

  @app.get("/{path:path}", include_in_schema=False)
  def client(path: str):
    if path.startswith(("api/", "ws/")):
      raise fastapi.HTTPException(404)
    target = os.path.normpath(os.path.join(settings.client_dir, path))
    if (
        path
        and target.startswith(os.path.normpath(settings.client_dir) + os.sep)
        and os.path.isfile(target)
    ):
      return responses.FileResponse(target)
    if os.path.isfile(index):
      return responses.FileResponse(index)
    return responses.PlainTextResponse(
        "The client is not built yet (scripts/build_client.sh).", 503
    )


def serve(settings: Optional[config_lib.Settings] = None) -> None:
  """Runs the site on settings.port and, unless 0, the watch app on
  settings.watch_port, in one process sharing one lobby."""
  import asyncio  # pylint: disable=g-import-not-at-top
  import uvicorn  # pylint: disable=g-import-not-at-top

  settings = settings or config_lib.from_env()
  main = create_app(settings)
  servers = [
      uvicorn.Server(uvicorn.Config(
          main, host=settings.host, port=settings.port, log_level="warning"
      ))
  ]
  if settings.watch_port:
    watch = create_watch_app(main.state.lobby, settings)
    servers.append(uvicorn.Server(uvicorn.Config(
        watch, host=settings.host, port=settings.watch_port,
        log_level="warning",
    )))
  print(
      f"Schnaps: http://{settings.host}:{settings.port}"
      + (f", all-cards watch on port {settings.watch_port}"
         if settings.watch_port else ""),
      flush=True,
  )

  async def run():
    await asyncio.gather(*(s.serve() for s in servers))

  asyncio.run(run())


def __getattr__(name: str):
  # `uvicorn schnaps_web.app:app` builds the real app (with the Neural
  # player) on first access, so importing this module stays cheap.
  if name == "app":
    global app  # pylint: disable=global-variable-undefined
    app = create_app()
    return app
  raise AttributeError(name)


if __name__ == "__main__":
  serve()
