"""The site's settings, from environment variables with defaults."""

import dataclasses
import os

_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)


@dataclasses.dataclass(frozen=True)
class Settings:
  """Settings.

  Attributes:
    host: the address to listen on (0.0.0.0: every interface, for the LAN).
    port: the port.
    watch_port: the all-cards watch port (read-only, every hand shown);
      0 turns it off.
    basic_model_dir: the Basic player's artifact dir (step 0).
    large_model_dir: the Large player's artifact dir (step 0); the bot is
      left out when it is not built.
    client_dir: the built client (client/dist), served at /.
    bot_delay: seconds a bot waits before each move, so people can follow.
    deal_pause: seconds the result of a deal stays up before the next one.
    max_tables: the most tables at once.
  """

  host: str = "0.0.0.0"
  port: int = 8000
  watch_port: int = 8001
  basic_model_dir: str = os.path.join(_ROOT, "models", "basic_player")
  large_model_dir: str = os.path.join(_ROOT, "models", "large_player")
  client_dir: str = os.path.join(_ROOT, "client", "dist")
  bot_delay: float = 0.8
  deal_pause: float = 5.0
  max_tables: int = 50


def from_env() -> Settings:
  """Settings with SCHNAPS_WEB_<FIELD> environment overrides."""
  kw = {}
  for f in dataclasses.fields(Settings):
    raw = os.environ.get(f"SCHNAPS_WEB_{f.name.upper()}")
    if raw is not None:
      kw[f.name] = type(f.default)(raw)
  return Settings(**kw)
