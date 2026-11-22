"""schnaps_web.game.bidding: bid estimates moved toward played results."""

import jax
import jax.numpy as jnp
import numpy as np
import pytest

from open_spiel.python.jax.games import schnaps as G
from open_spiel.python.scale.core import x64
from open_spiel.python.scale.envs import schnaps as schnaps_env
from schnaps_web.game import bidding
from schnaps_web.game import success

x64.enable_x64()


def _info(seat, trump, cards):
  hand = np.zeros((1, 20), bool)
  hand[0, list(cards)] = True
  return {
      "seat": jnp.asarray([seat], jnp.int32),
      "trump": jnp.asarray([trump], jnp.int32),
      "hand": jnp.asarray(hand),
  }


def _int_key(text):
  m = [int(x) for x in text.split(",")]
  return ((m[0] * 32 + m[1]) * 32 + m[2]) * 32 + m[3]


def test_hand_keys_match_the_class_keys():
  rng = np.random.default_rng(0)
  for _ in range(200):
    cards = rng.choice(20, 5, replace=False).tolist()
    trump = int(rng.integers(4))
    marked, plain = bidding.hand_keys(_info(0, trump, cards))
    assert int(marked[0]) == _int_key(success.class_key(cards, trump, True))
    assert int(plain[0]) == _int_key(success.class_key(cards, None, False))


def test_lookup_finds_entries_and_misses_with_zero():
  table = bidding.PlayedTable({"lomt": {"keys": [12, 4, 40], "n": [3, 1, 9], "wins": [2, 0, 9]}})
  n, w = table.lookup("lomt", jnp.asarray([4, 12, 40, 5, 99], jnp.int32))
  assert np.asarray(n).tolist() == [1, 3, 9, 0, 0]
  assert np.asarray(w).tolist() == [0, 2, 9, 0, 0]
  n, w = table.lookup("bauern", jnp.asarray([4], jnp.int32))  # an empty game
  assert float(n[0]) == 0 and float(w[0]) == 0


def test_the_site_table_loads():
  table = bidding.load_played_table()
  assert table is not None, "game/played_table.json is missing (scripts/build_played_table.py)"
  for g in bidding.PLAYED_GAMES:
    keys, n, wins = table.games[g]
    assert keys.size > 0 and np.all(np.diff(keys) > 0) and np.all(wins <= n)


def _first_bid(seed):
  """A random deal's first bidder: (info batch of 1, legal batch of 1)."""
  env = schnaps_env.SchnapsEnv()
  rng = np.random.default_rng(seed)
  s = env.init(jax.random.key(seed))
  while int(s.phase) != G.PHASE_BIDDING:
    a = rng.choice(np.flatnonzero(np.asarray(env.legal_mask(s))))
    s = env.step(s, jnp.int32(a), jax.random.key(seed + 1000))
  seat = env.actor(s)
  info = jax.tree.map(lambda x: jnp.asarray(x)[None], env.info_state(s, seat))
  return info, jnp.asarray(env.legal_mask(s))[None]


def _const(values):
  return lambda info, contract: jnp.full(
      info["seat"].shape, jnp.asarray(values, jnp.float32)[contract]
  )


@pytest.mark.parametrize("n,wins", [(0, 0), (16, 16), (48, 0)])
def test_estimates_move_toward_the_played_rate(n, wins):
  info, legal = _first_bid(3)
  seat = int(info["seat"][0])
  marked, plain = bidding.hand_keys(info)
  key = int(plain[0]) * 4
  table = bidding.PlayedTable({"lomt": {"keys": [key], "n": [n], "wins": [wins]}})
  values = [0.0, 0.0, 0.0, 0.0]  # p_net = 0.5 everywhere
  plain_est = bidding.estimate(info, legal, _const(values))
  est = bidding.estimate(info, legal, _const(values), table, prior=16.0)
  lomt = bidding.call_action(G.LOMT)
  p = (wins + 16 * 0.5) / (n + 16)
  assert float(est.value[0, lomt]) == pytest.approx(G.CONTRACT_POINTS[G.LOMT] * (2 * p - 1), abs=1e-5)
  # Nothing else had played results.
  other = np.arange(bidding.NUM_ACTIONS) != lomt
  np.testing.assert_allclose(np.asarray(est.value)[0, other], np.asarray(plain_est.value)[0, other])
  del seat, marked


def test_partner_schnapser_reads_its_own_table_and_seats_1_3_none():
  info, legal = _first_bid(5)
  marked, _ = bidding.hand_keys(info)
  k = int(marked[0]) * 4
  table = bidding.PlayedTable({
      "schnapser_caller": {"keys": [k], "n": [10], "wins": [10]},
      "schnapser_partner": {"keys": [k + 2], "n": [10], "wins": [0]},
  })
  for seat, want in [(0, 10.0), (2, 0.0), (1, None), (3, None)]:
    n, w = bidding.played_results(table, dict(info, seat=jnp.asarray([seat], jnp.int32)), G.SCHNAPSER)
    if want is None:
      assert float(n[0]) == 0
    else:
      assert float(n[0]) == 10 and float(w[0]) == want
