"""schnaps_web.deal: whole deals, privacy of frames, turn checks."""

import random

import pyspiel
import pytest

from schnaps_web import deal as deal_lib
from schnaps_web import match


@pytest.fixture(scope="module")
def game():
  return pyspiel.load_game(deal_lib.GAME_STRING)


def _random_deal(game, dealer, seed, check=None):
  rng = random.Random(seed)
  d = deal_lib.Deal(game, dealer, rng)
  while not d.is_over:
    if check:
      check(d)
    seat = d.to_move()
    legal = d.state.legal_actions()
    a = rng.choice(legal)
    if 32 in legal and rng.random() < 0.7:
      a = 32  # mostly pass, so some deals stay Normal
    d.apply(seat, a)
  return d


def test_whole_deals_and_results(game):
  contracts = set()
  for seed in range(40):
    dealer = seed % 4
    d = _random_deal(game, dealer, seed)
    res = d.result()
    assert res["returns"] == list(d.state.returns())
    pair, points = match.deal_winner(res["returns"], dealer)
    assert points > 0 and pair in (0, 1)
    contracts.add(res["contract"])
    if res["contract"] == "Normal":
      assert res["declarer"] is None
    else:
      assert 0 <= res["declarer"] < 4
  assert "Normal" in contracts and len(contracts) > 2


def test_the_caller_sits_left_of_the_dealer(game):
  for dealer in range(4):
    d = deal_lib.Deal(game, dealer, random.Random(dealer))
    # The first decision is the trump choice, by the Caller.
    assert d.to_move() == (dealer + 1) % 4
    assert d.frame(None)["seatMap"][0] == (dealer + 1) % 4


def _check_privacy(d):
  for seat in range(4):
    f = d.frame(seat)
    me = f["viewer"]["seat"]
    assert me == d.game_seat(seat)
    for entry in f["presentation"]["view"]["seats"]:
      if entry["seat"] != me:
        assert all(c is None for c in entry["cards"])
    if d.to_move() == seat:
      ids = sorted(a["id"] for a in f["presentation"]["actions"])
      assert ids == sorted(d.state.legal_actions())
    else:
      assert f["presentation"]["actions"] == []
  spectator = d.frame(None)
  assert spectator["viewer"]["seat"] is None
  assert spectator["presentation"]["actions"] == []
  for entry in spectator["presentation"]["view"]["seats"]:
    assert all(c is None for c in entry["cards"])


def test_frames_hide_other_hands(game):
  for seed in range(6):
    _random_deal(game, seed % 4, 100 + seed, check=_check_privacy)


def test_moves_out_of_turn_or_illegal_are_refused(game):
  d = deal_lib.Deal(game, 0, random.Random(1))
  mover = d.to_move()
  other = (mover + 1) % 4
  legal = d.state.legal_actions()
  with pytest.raises(deal_lib.DealError):
    d.apply(other, legal[0])
  illegal = next(a for a in range(39) if a not in legal)
  with pytest.raises(deal_lib.DealError):
    d.apply(mover, illegal)
  with pytest.raises(deal_lib.DealError):
    d.result()
  finished = _random_deal(game, 0, 2)
  with pytest.raises(deal_lib.DealError):
    finished.apply(0, 0)
  assert finished.frame(0)["returns"] is not None
