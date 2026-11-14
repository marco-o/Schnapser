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
  DELETE /api/tables/{id}                   the creator closes the table

WebSocket /ws/tables/{id}?token=...: the table's snapshot (table.snapshot)
on connect and after every change, as seen by that token (no token: a
spectator).

Everything else serves the built client (client/dist), with index.html for
the client's own routes.

  uvicorn schnaps_web.app:app --host 0.0.0.0 --port 8000
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
    bots: the bot catalog (default: bots.make_bots, which loads the Neural
      player).

  Returns:
    The FastAPI app.
  """
  settings = settings or config_lib.from_env()
  if bots is None:
    bots = bots_lib.make_bots(settings.model_dir)
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

  @app.delete("/api/tables/{table_id}")
  async def close(table_id: str, x_seat_token: Optional[str] = fastapi.Header(None)):
    guarded(table_of(table_id).close, x_seat_token)
    return {"ok": True}

  @app.websocket("/ws/tables/{table_id}")
  async def watch(websocket: fastapi.WebSocket, table_id: str):
    try:
      table = lobby.get(table_id)
    except KeyError:
      await websocket.close(code=4404)
      return
    await websocket.accept()
    token = websocket.query_params.get("token") or None
    listener = table_lib.Listener(token, websocket.send_json)
    await table.attach(listener)
    try:
      while True:
        await websocket.receive_text()  # keep-alive pings; nothing else
    except fastapi.WebSocketDisconnect:
      pass
    finally:
      table.detach(listener)

  # The client: built files, and index.html for its own routes.
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

  return app


def __getattr__(name: str):
  # `uvicorn schnaps_web.app:app` builds the real app (with the Neural
  # player) on first access, so importing this module stays cheap.
  if name == "app":
    global app  # pylint: disable=global-variable-undefined
    app = create_app()
    return app
  raise AttributeError(name)
