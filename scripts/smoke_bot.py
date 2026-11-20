"""Plays one deal with the site's Basic player on all four seats (argv[1]: another model folder)."""
import os
import random

import pyspiel

from schnaps_web.game import player  # noqa: F401  registers schnaps_web.player
from open_spiel.python.scale.serve import checkpoint_bot

import sys
MODEL = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(__file__), "..", "models", "basic_player")
bot = checkpoint_bot.checkpoint_bot(os.path.abspath(MODEL), step=0)
print(bot)
game = pyspiel.load_game("schnaps(max_flecks=2)")
state = game.new_initial_state()
rng = random.Random(0)
import time
times = []
while not state.is_terminal():
  if state.is_chance_node():
    acts, probs = zip(*state.chance_outcomes())
    state.apply_action(rng.choices(acts, probs)[0])
  else:
    t = time.time()
    a = bot.choose_action(state, state.current_player())
    times.append(time.time() - t)
    print(state.current_player(), state.action_to_string(a))
    state.apply_action(a)
print("returns", state.returns())
print("first move %.1fs, then mean %.3fs" % (times[0], sum(times[1:]) / len(times[1:])))
