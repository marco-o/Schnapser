"""The bots a table creator can seat.

A bot chooses a legal action for the game seat to move on a pyspiel state.
Choosing may block (a network runs), so tables call it in a worker thread;
each bot serialises its own calls.

  * "neural": the Neural player (game/player.py): value-head bidding and one
    network per contract, loaded from models/neural_player (step 0).
  * "random": a uniformly random legal move (tests; not offered by default).

A new bot is one class with `name`, `label` and `choose(state, seat)`, and
one entry in `make_bots`.
"""

import random
import threading
from typing import Protocol

import pyspiel


class Bot(Protocol):
  """Chooses moves.

  Attributes:
    name: the catalog key.
    label: what the site shows.
  """

  name: str
  label: str

  def choose(self, state: pyspiel.State, seat: int) -> int:
    """A legal action for game seat `seat`, who is to move."""
    ...


class RandomBot:
  """A uniformly random legal move."""

  name = "random"
  label = "Random"

  def __init__(self, seed: int = 0):
    self._rng = random.Random(seed)
    self._lock = threading.Lock()

  def choose(self, state: pyspiel.State, seat: int) -> int:
    del seat
    with self._lock:
      return self._rng.choice(state.legal_actions())


class NeuralBot:
  """The Neural player, loaded once and compiled at start."""

  name = "neural"
  label = "Neural player"

  def __init__(self, model_dir: str, warmup: bool = True):
    # Imported here: they pull in JAX and the scale framework.
    from open_spiel.python.scale.serve import checkpoint_bot  # pylint: disable=g-import-not-at-top
    from schnaps_web.game import player  # pylint: disable=g-import-not-at-top,unused-import  # registers schnaps_web.player

    self._bot = checkpoint_bot.checkpoint_bot(model_dir, step=0)
    self._lock = threading.Lock()
    if warmup:
      self._bot.warmup(range(4))

  def choose(self, state: pyspiel.State, seat: int) -> int:
    with self._lock:
      return self._bot.choose_action(state, seat)


def make_bots(model_dir: str, *, include_random: bool = False) -> dict:
  """The bot catalog: {name: Bot}.

  Args:
    model_dir: the Neural player's artifact dir.
    include_random: also offer the random bot.

  Returns:
    The catalog.
  """
  bots = {"neural": NeuralBot(model_dir)}
  if include_random:
    bots["random"] = RandomBot()
  return bots
