"""schnaps_web.game.bidding.allowed_bids: the bots' two hard bidding rules."""

import jax.numpy as jnp
import numpy as np
import pytest

from schnaps_web.game import bidding

PASS, FLECK = bidding.PASS, bidding.FLECK
SCHNAPSER = bidding.call_action(1)
LOMT = bidding.call_action(2)
BAUERN = bidding.call_action(3)
AS = 4  # rank Unter..As = 0..4; card = suit * 5 + rank


def _info(seat, trump, cards, declarer=0):
  hand = np.zeros((1, 20), bool)
  hand[0, list(cards)] = True
  return {
      "seat": jnp.asarray([seat], jnp.int32),
      "declarer": jnp.asarray([declarer], jnp.int32),
      "trump": jnp.asarray([trump], jnp.int32),
      "hand": jnp.asarray(hand),
  }


def _legal(*actions):
  m = np.zeros((1, bidding.NUM_ACTIONS), bool)
  m[0, list(actions)] = True
  return jnp.asarray(m)


ALL = _legal(PASS, FLECK, SCHNAPSER, LOMT, BAUERN)
#: Herz trump (suit 0): the trump As, Zehn, Koenig, Ober and the Caro As.
WITH_AS = (0 * 5 + AS, 3, 2, 1, 1 * 5 + AS)
#: The same, with the Unter instead of the trump As.
WITHOUT_AS = (0, 3, 2, 1, 1 * 5 + AS)


@pytest.mark.parametrize("seat,ok", [(0, True), (1, False), (2, True), (3, False)])
def test_schnapser_only_over_our_own_normal_game(seat, ok):
  got = np.asarray(bidding.allowed_bids(_info(seat, 0, WITH_AS), ALL)[0])
  assert got[SCHNAPSER] == ok
  assert got[PASS] and got[FLECK] and got[LOMT] and got[BAUERN]


@pytest.mark.parametrize("trump", range(4))
def test_bauern_needs_the_trump_as(trump):
  shift = lambda cards: [((c // 5 + trump) % 4) * 5 + c % 5 for c in cards]  # noqa: E731
  with_as = bidding.allowed_bids(_info(0, trump, shift(WITH_AS)), ALL)
  without = bidding.allowed_bids(_info(0, trump, shift(WITHOUT_AS)), ALL)
  assert bool(with_as[0, BAUERN]) and not bool(without[0, BAUERN])
  # Only the Bauern goes; the As of another suit does not count.
  assert np.array_equal(
      np.asarray(without[0]), np.asarray(ALL[0]).copy() & (np.arange(39) != BAUERN)
  )


def test_the_set_rule_plays_for_the_set_win():
  rule = bidding.make_rule("set_aware")
  assert rule.kwargs()["value"] == "win"
  w = bidding.set_win_table()
  np.testing.assert_allclose(w[1:, 1:] + w[1:, 1:].T, 1.0, atol=1e-9)
  assert w[3, 25] > 0.9


def test_illegal_bids_stay_illegal():
  legal = _legal(PASS)
  got = bidding.allowed_bids(_info(0, 0, WITH_AS), legal)
  assert np.array_equal(np.asarray(got), np.asarray(legal))
