"""The web app: the lobby and table API, a WebSocket per table, the client.

REST (JSON; a seat token goes in the X-Seat-Token header):

  GET    /api/bots                          the bot catalog
  GET    /api/tables                        the lobby's tables
  POST   /api/tables                        {name, player, seat} -> {id, token}
  POST   /api/tables/{id}/seats/{n}         {player} -> {token}: take a seat
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
/api/tables and the WebSocket, which shows every hand to everyone.

Everything else serves the built client (client/dist), with index.html for
the client's own routes.

  python -m schnaps_web.app        # both ports (serve)
"""

import os
from typing import Any, Optional

import fastapi
from fastapi import responses
from fastapi import staticfiles

from schnaps_web import bots as bots_lib
from schnaps_web import config as config_lib
from schnaps_web import lobby as lobby_lib
from schnaps_web import table as table_lib


def create_app(
    settings: Optional[config_lib.Settings] = None,
    bots: Optional[dict] = None,
) -> fastapi.FastAPI:
  """The app.

  Args:
    settings: the settings (default: config.from_env()).
    bots: the bot catalog (default: bots.make_bots, which loads the Basic
      and, when built, the Large player).

  Returns:
    The FastAPI app.
  """
  settings = settings or config_lib.from_env()
  if bots is None:
    bots = bots_lib.make_bots(
        settings.basic_model_dir, settings.large_model_dir
    )
  lobby = lobby_lib.Lobby(bots, settings)
  app = fastapi.FastAPI(title="Schnaps")
  app.state.lobby = lobby

  def table_of(table_id: str) -> table_lib.Table:
    try:
      return lobby.get(table_id)
    except KeyError:
      raise fastapi.HTTPException(404, "no such table") from None

  def guarded(fn, *args):
    try:
      return fn(*args)
    except table_lib.Forbidden as e:
      raise fastapi.HTTPException(403, str(e)) from None
    except table_lib.TableError as e:
      raise fastapi.HTTPException(400, str(e)) from None

  def body_field(body: Any, key: str):
    if not isinstance(body, dict) or key not in body:
      raise fastapi.HTTPException(400, f"missing {key!r}")
    return body[key]

  @app.get("/api/site")
  async def site():
    return {"watch": False}

  @app.get("/api/bots")
  async def list_bots():
    return [{"name": b.name, "label": b.label} for b in bots.values()]

  @app.get("/api/tables")
  async def list_tables():
    return lobby.summaries()

  @app.post("/api/tables")
  async def create_table(body: dict = fastapi.Body(...)):
    table, token = guarded(
        lobby.create,
        body_field(body, "name"),
        body_field(body, "player"),
        body.get("seat", 0),
        body.get("lang"),
    )
    return {"id": table.id, "token": token}

  @app.post("/api/tables/{table_id}/seats/{seat}")
  async def take_seat(table_id: str, seat: int, body: dict = fastapi.Body(...)):
    table = table_of(table_id)
    return {"token": guarded(table.sit, seat, body_field(body, "player"))}

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

  _add_socket(app, lobby, reveal=True)
  _add_client(app, settings)
  return app


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
