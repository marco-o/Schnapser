"""The bots a table creator can seat.

A bot chooses a legal action for the game seat to move on a pyspiel state.
Choosing may block (a network runs), so tables call it in a worker thread;
each bot serialises its own calls.

  * "basic" (Bologna) and "large" (Firenze): neural players (game/player.py), value-head bidding
    and one network per contract, loaded from models/basic_player and
    models/large_player (step 0). They differ in the Normal network: Basic
    has the compact CPU-trained one, Large the bigger GPU-trained one. Large
    is offered only when its model is built (scripts/build_large.sh).
  * "2a" (Verona): the same bidder, but ONE network plays every contract
    (game/player_one.py; step 2a, Docker/step2a-options.md), loaded from
    models/mixed_player. Offered only when built (scripts/build_mixed.sh).
  * "napoli" (Napoli): determinized search for the card play
    (game/search.py: samples the hidden hands consistent with what its seat
    knows, solves each deal exactly, plays the best mean); the trump choice
    and the bidding are Bologna's.
  * "random": a uniformly random legal move (tests; not offered by default).

A new bot is one class with `name`, `label` and `choose(state, seat)`, and
one entry in `make_bots`. The labels (what the site shows) are
rating.BOT_LABELS; ratings go by `name`, so a label can change freely.
"""

import random
import threading
from typing import Optional, Protocol

import pyspiel

from schnaps_web import rating


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
  """A neural player, loaded once and compiled at start.

  It replays the deal's history into the JAX game, reads the seat's view
  (envs.schnaps InfoState) and plays the player policy's most likely legal
  move. The set situation, when known, goes into the view as "set_need"
  (points each partnership still needs, game partnership 0 first), which
  the "set_aware" bid rule reads (game/bidding.py).
  """

  def __init__(
      self,
      model_dir: str,
      warmup: bool = True,
      name: str = "basic",
      label: str = "Bologna",
  ):
    self.name = name
    self.label = label
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
    from schnaps_web.game import player_one  # schnaps_web.player_one
    # pylint: enable=g-import-not-at-top
    del player, player_one

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
      raise ValueError(f"the {self.label} player chose an illegal move {action}")
    return action


class SearchBot:
  """Searches the card play (game/search.py); another bot does the rest.

  Args:
    bidder: plays every move outside the card play (the trump choice and
      the bidding).
    n_samples: deals sampled per card-play decision.
  """

  def __init__(self, bidder, n_samples: int = 20, name: str = "napoli",
               label: str = "Napoli", seed: int = 0):
    from schnaps_web.game import search  # pylint: disable=g-import-not-at-top

    self.name = name
    self.label = label
    self._bidder = bidder
    self._searcher = search.Searcher(n_samples, seed)
    self._lock = threading.Lock()

  def choose(self, state: pyspiel.State, seat: int, set_need=None) -> int:
    if not _in_play(state):
      return self._bidder.choose(state, seat, set_need)
    with self._lock:
      action = self._searcher.decide(state, seat)
    if action not in state.legal_actions():
      raise ValueError(f"the {self.label} player chose an illegal move {action}")
    return action


def _in_play(state: pyspiel.State) -> bool:
  """Whether the deal is in the card play (its text says "Phase: Play")."""
  return any(line.strip() == "Phase: Play" for line in str(state).splitlines())


def make_bots(
    basic_model_dir: str,
    large_model_dir: Optional[str] = None,
    mixed_model_dir: Optional[str] = None,
    *,
    include_random: bool = False,
    search_samples: int = 50,
) -> dict:
  """The bot catalog: {name: Bot}.

  Args:
    basic_model_dir: the Basic player's artifact dir.
    large_model_dir: the Large player's artifact dir; left out when None or
      not built.
    mixed_model_dir: the 2a player's artifact dir (one network for every
      contract); left out when None or not built.
    include_random: also offer the random bot.
    search_samples: deals Napoli samples per card-play decision (0 leaves
      Napoli out).

  Returns:
    The catalog.
  """
  # pylint: disable-next=g-import-not-at-top
  from open_spiel.python.scale.ckpt import artifact

  def neural(model_dir, name):
    return NeuralBot(model_dir, name=name, label=rating.bot_label(name))

  bots = {"basic": neural(basic_model_dir, "basic")}
  if large_model_dir and artifact.exists(large_model_dir, 0):
    bots["large"] = neural(large_model_dir, "large")
  if mixed_model_dir and artifact.exists(mixed_model_dir, 0):
    bots["2a"] = neural(mixed_model_dir, "2a")
  if search_samples > 0:
    bots["napoli"] = SearchBot(
        bots["basic"], search_samples, label=rating.bot_label("napoli")
    )
  if include_random:
    bots["random"] = RandomBot()
  return bots
