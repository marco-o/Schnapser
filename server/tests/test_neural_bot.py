"""schnaps_web.bots.NeuralBot: the real models play legal moves, with a set."""

import os
import random

import pyspiel
import pytest

from schnaps_web import bots as bots_lib
from schnaps_web import config as config_lib

SETTINGS = config_lib.Settings()
MODELS = {
    "basic": (SETTINGS.basic_model_dir, "scripts/build_model.sh"),
    "large": (SETTINGS.large_model_dir, "scripts/build_large.sh"),
    "2a": (SETTINGS.mixed_model_dir, "scripts/build_mixed.sh"),
}


@pytest.fixture(scope="module", params=sorted(MODELS))
def bot(request):
  model, script = MODELS[request.param]
  if not os.path.isdir(os.path.join(model, "0")):
    pytest.skip(f"{model} is not built ({script})")
  return bots_lib.NeuralBot(
      model, warmup=False, name=request.param, label=request.param.title()
  )


@pytest.mark.parametrize("set_need", [None, (31, 31), (4, 25), (25, 4)])
def test_plays_whole_deals(bot, set_need):
  game = pyspiel.load_game("schnaps(max_flecks=2)")
  rng = random.Random(7)
  state = game.new_initial_state()
  while not state.is_terminal():
    if state.is_chance_node():
      acts, probs = zip(*state.chance_outcomes())
      state.apply_action(rng.choices(acts, probs)[0])
      continue
    action = bot.choose(state, state.current_player(), set_need)
    assert action in state.legal_actions()
    state.apply_action(action)
  assert max(state.returns()) > 0


def test_the_model_bids_with_the_set_aware_rule(bot):
  assert bot.rule is not None and bot.rule.name == "set_aware"


def test_the_catalog_offers_every_player_when_built():
  if not all(os.path.isdir(os.path.join(m, "0")) for m, _ in MODELS.values()):
    pytest.skip("every player must be built")
  catalog = bots_lib.make_bots(
      SETTINGS.basic_model_dir,
      SETTINGS.large_model_dir,
      SETTINGS.mixed_model_dir,
  )
  assert [(b.name, b.label) for b in catalog.values()] == [
      ("basic", "Bologna"),
      ("large", "Firenze"),
      ("2a", "Verona"),
      ("napoli", "Napoli"),
  ]
