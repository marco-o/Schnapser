"""schnaps_web.bots.NeuralBot: the real model plays legal moves, with a set."""

import os
import random

import pyspiel
import pytest

from schnaps_web import bots as bots_lib
from schnaps_web import config as config_lib

MODEL = config_lib.Settings().model_dir


@pytest.fixture(scope="module")
def bot():
  if not os.path.isdir(os.path.join(MODEL, "0")):
    pytest.skip("models/neural_player is not built (scripts/build_model.sh)")
  return bots_lib.NeuralBot(MODEL, warmup=False)


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
