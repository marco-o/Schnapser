"""schnaps_web.game.search and the Napoli bot: fair sampling, legal moves."""

import random
import time

import pyspiel
import pytest

from schnaps_web import bots as bots_lib
from schnaps_web import deal as deal_lib
from schnaps_web.game import oracle
from schnaps_web.game import search


@pytest.fixture(scope="module")
def game():
  return pyspiel.load_game(deal_lib.GAME_STRING)


def _in_play(state):
  return bots_lib._in_play(state)  # pylint: disable=protected-access


def _play_positions(game, seed, n=40):
  """States in the card play from random deals (random moves, mostly
  passing in the bidding so some stay Normal)."""
  rng = random.Random(seed)
  out = []
  while len(out) < n:
    s = game.new_initial_state()
    while not s.is_terminal():
      if s.is_chance_node():
        acts, probs = zip(*s.chance_outcomes())
        s.apply_action(rng.choices(acts, probs)[0])
        continue
      legal = s.legal_actions()
      if _in_play(s):
        out.append(s.clone())
      a = 32 if 32 in legal and rng.random() < 0.6 else rng.choice(legal)
      s.apply_action(a)
  return out


def test_the_true_deal_is_always_consistent(game):
  """Whatever a seat infers, the real holder of every hidden card stays
  allowed (or known), and the counts add up."""
  for s in _play_positions(game, 0, 200):
    pos = oracle.position(s)
    seat = s.current_player()
    plays = search.public_plays(s)
    known, allowed, need = search.constraints(
        pos.rules, plays, pos.play[0][seat], seat
    )
    held = pos.play[0]
    for c, p in known.items():
      assert held[p] >> c & 1
    for c, seats in allowed.items():
      holder = next(p for p in range(4) if held[p] >> c & 1)
      assert holder in seats and holder != seat
    for p in range(4):
      if p != seat:
        assert need[p] == bin(held[p]).count("1") - sum(
            1 for c, q in known.items() if q == p
        )


def test_samples_keep_the_seats_hand_and_the_sizes(game):
  rng = random.Random(1)
  for s in _play_positions(game, 2, 100):
    pos = oracle.position(s)
    seat = s.current_player()
    plays = search.public_plays(s)
    held = search.sample_hands(pos.rules, plays, pos.play[0][seat], seat, rng)
    assert held is not None
    assert held[seat] == pos.play[0][seat]
    for p in range(4):
      assert bin(held[p]).count("1") == bin(pos.play[0][p]).count("1")
    all_cards = 0
    for h in held:
      assert all_cards & h == 0
      all_cards |= h
    # The replay from the sample reaches the same public position.
    q = search.replay(pos.rules, held, plays)
    assert q[1:] == pos.play[1:]


def test_a_void_is_respected():
  """A seat that did not follow suit never gets that suit back."""
  rules = oracle.Rules(trump=0, contract=oracle.LOMT, declarer=0)
  # Seat 0 leads the As of suit 1; seat 1 plays a suit-2 card (void in 1).
  plays = [(0, 1 * 5 + 4), (1, 2 * 5 + 0)]
  hand = sum(1 << c for c in (2 * 5 + 4, 3 * 5 + 4, 3 * 5 + 3, 0 * 5 + 4))
  rng = random.Random(0)
  for _ in range(200):
    held = search.sample_hands(rules, plays, hand, 0, rng)
    assert held is not None
    assert not any(held[1] >> (1 * 5 + r) & 1 for r in range(5))


def test_napoli_plays_whole_deals_legally(game):
  bidder = bots_lib.RandomBot(seed=3)
  napoli = bots_lib.SearchBot(bidder, n_samples=4)
  rng = random.Random(5)
  for _ in range(6):
    s = game.new_initial_state()
    while not s.is_terminal():
      if s.is_chance_node():
        acts, probs = zip(*s.chance_outcomes())
        s.apply_action(rng.choices(acts, probs)[0])
        continue
      a = napoli.choose(s, s.current_player())
      assert a in s.legal_actions()
      s.apply_action(a)
  assert napoli._searcher.failed_samples == 0  # pylint: disable=protected-access


def test_a_first_trick_decision_is_quick_enough(game):
  """The worst case (the opening lead, 15 hidden cards) at the site's 20
  samples stays within a few seconds."""
  firsts = [
      s for s in _play_positions(game, 9, 60)
      if not search.public_plays(s)
  ][:3]
  assert firsts
  searcher = search.Searcher(20)
  t = time.perf_counter()
  for s in firsts:
    searcher.decide(s, s.current_player())
  per = (time.perf_counter() - t) / len(firsts)
  print(f"opening lead: {per:.2f} s per decision at 20 samples")
  assert per < 10
