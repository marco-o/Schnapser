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

  def choose(
      self, state: pyspiel.State, seat: int, set_need=None
  ) -> int:
    """A legal action for game seat `seat`, who is to move.

    `set_need` is (points game partnership 0 still needs, partnership 1),
    or None outside a set.
    """
    ...


class RandomBot:
  """A uniformly random legal move."""

  name = "random"
  label = "Random"

  def __init__(self, seed: int = 0):
    self._rng = random.Random(seed)
    self._lock = threading.Lock()

  def choose(self, state: pyspiel.State, seat: int, set_need=None) -> int:
    del seat, set_need
    with self._lock:
      return self._rng.choice(state.legal_actions())


#: The longest history replayed (deal, trump, bids and plays fit easily).
_MAX_HISTORY = 96


class NeuralBot:
  """The Neural player, loaded once and compiled at start.

  It replays the deal's history into the JAX game, reads the seat's view
  (envs.schnaps InfoState) and plays the player policy's most likely legal
  move. The set situation, when known, goes into the view as "set_need"
  (points each partnership still needs, game partnership 0 first), which
  the "set_aware" bid rule reads (game/bidding.py).
  """

  name = "neural"
  label = "Neural player"

  def __init__(self, model_dir: str, warmup: bool = True):
    # Imported here: they pull in JAX and the scale framework.
    # pylint: disable=g-import-not-at-top
    import jax
    import jax.numpy as jnp
    import numpy as np

    from open_spiel.python.scale.ckpt import artifact
    from open_spiel.python.scale.core import types
    from open_spiel.python.scale.core import x64
    from open_spiel.python.scale.envs import schnaps as schnaps_env
    from schnaps_web.game import player  # registers schnaps_web.player
    # pylint: enable=g-import-not-at-top
    del player

    x64.enable_x64()
    art = artifact.load_artifact(model_dir, 0)
    policy, params = art.policy, art.params
    self.rule = getattr(policy, "rule", None)
    env = schnaps_env.SchnapsEnv()
    game = env.game
    self._np = np
    self._lock = threading.Lock()

    def decide(history, n, seat, set_need, known):
      def body(i, s):
        nxt = game.apply_action(s, history[i])
        return jax.tree.map(lambda a, b: jnp.where(i < n, a, b), nxt, s)

      s = jax.lax.fori_loop(0, _MAX_HISTORY, body, game.new_initial_state())
      info = jax.tree.map(lambda x: jnp.asarray(x)[None], env.info_state(s, seat))
      if known:
        info["set_need"] = set_need[None]
      legal = jnp.asarray(env.legal_mask(s))[None]
      seats = jnp.asarray([seat], jnp.int32)
      step = types.SeatStep(
          info=info,
          legal_mask=legal,
          seat=seats,
          to_move=seats,
          new_hand=jnp.zeros((1,), jnp.bool_),
          new_match=jnp.zeros((1,), jnp.bool_),
          last_action=jnp.full((1,), types.NO_ACTION, jnp.int32),
          last_actor=jnp.full((1,), types.NO_ACTOR, jnp.int32),
      )
      key = jax.random.key(0)
      carry = policy.init_carry(params, 1, seats, key)
      out = policy.evaluate(params, carry, step, key)
      logits = jnp.where(legal, out.logits, -jnp.inf)
      return jnp.argmax(logits, axis=-1)[0]

    self._decide = jax.jit(decide, static_argnums=(4,))
    if warmup:
      self._warm()

  def _warm(self) -> None:
    """Compiles both variants (with and without the set) on a real deal."""
    import random  # pylint: disable=g-import-not-at-top

    g = pyspiel.load_game("schnaps(max_flecks=2)")
    state = g.new_initial_state()
    rng = random.Random(0)
    while state.is_chance_node():
      acts, probs = zip(*state.chance_outcomes())
      state.apply_action(rng.choices(acts, probs)[0])
    self.choose(state, state.current_player())
    self.choose(state, state.current_player(), (31, 31))

  def choose(self, state: pyspiel.State, seat: int, set_need=None) -> int:
    np = self._np
    history = state.history()
    if len(history) > _MAX_HISTORY:
      raise ValueError(f"a history of {len(history)} moves is too long")
    padded = np.zeros(_MAX_HISTORY, np.int32)
    padded[: len(history)] = history
    known = set_need is not None
    need = np.asarray(set_need if known else (0, 0), np.int32)
    with self._lock:
      action = int(self._decide(padded, len(history), seat, need, known))
    if action not in state.legal_actions():
      raise ValueError(f"the Neural player chose an illegal move {action}")
    return action


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
