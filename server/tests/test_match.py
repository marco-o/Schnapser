"""schnaps_web.match: seat mapping, dealer rotation, sets and matches."""

import pytest

from schnaps_web import match as m


def test_caller_is_left_of_the_dealer_and_turns_go_clockwise():
  for dealer in range(4):
    caller = m.caller_of(dealer)
    assert caller == (dealer + 1) % 4
    # Game seats 0..3 walk clockwise from the Caller.
    seats = [m.table_seat(g, dealer) for g in range(4)]
    assert seats == [(caller + g) % 4 for g in range(4)]
    for g in range(4):
      assert m.game_seat(m.table_seat(g, dealer), dealer) == g


def test_game_partnerships_are_table_pairs():
  # Game seats 0 and 2 are partners, so they must be one table pair.
  for dealer in range(4):
    assert m.pair_of(m.table_seat(0, dealer)) == m.pair_of(
        m.table_seat(2, dealer)
    )
    assert m.pair_of(m.table_seat(1, dealer)) != m.pair_of(
        m.table_seat(0, dealer)
    )


def test_deal_winner_credits_the_table_pair():
  # Dealer 0: the Caller is table seat 1, so game seats 0/2 are table 1/3.
  assert m.deal_winner([3, -3, 3, -3], dealer=0) == (1, 3)
  assert m.deal_winner([-2, 2, -2, 2], dealer=0) == (0, 2)
  # Dealer 1: the Caller is table seat 2 (pair 0).
  assert m.deal_winner([1, -1, 1, -1], dealer=1) == (0, 1)
  with pytest.raises(ValueError):
    m.deal_winner([0, 0, 0, 0], dealer=0)


def test_a_failed_contract_scores_for_the_opponents():
  match = m.Match(dealer=3)  # the Caller is table seat 0
  # Game seat 1 (table seat 1, pair 1) called Bauern with a fleck and failed:
  # the other side (game seats 0/2, table pair 0) wins 24.
  out = match.record([24, -24, 24, -24], "Bauern", 1, 1)
  deal = out["deal"]
  assert deal.declarer == 1 and deal.winner == 0 and deal.points == 24
  assert match.need == [7, 31]
  assert deal.need_after == (7, 31)


def test_dealer_rotates_clockwise():
  match = m.Match(dealer=2)
  dealers = []
  for _ in range(5):
    dealers.append(match.dealer)
    match.record([1, -1, 1, -1], "Normal", None, 0)
  assert dealers == [2, 3, 0, 1, 2]


def test_sets_and_the_match():
  match = m.Match(dealer=3)  # Caller table seat 0: game seats 0/2 = pair 0
  def win_for(pair, points):
    # Pick the game seats of `pair` for the current dealer.
    caller_pair = m.pair_of(match.caller)
    sign = 1 if pair == caller_pair else -1
    return match.record(
        [sign * points, -sign * points] * 2, "Lomt", 0, 0
    )

  out = None
  for _ in range(3):
    out = win_for(0, 9)  # 31 -> 22 -> 13 -> 4
  assert match.need == [4, 31] and out["set_winner"] is None
  out = win_for(0, 9)  # 4 - 9 < 0: pair 0 wins set 1
  assert out["set_winner"] == 0 and out["match_winner"] is None
  assert match.sets == [1, 0] and match.need == [31, 31]
  assert match.set_number == 2
  assert out["deal"].need_after == (-5, 31)
  for _ in range(3):
    win_for(1, 12)  # 31 -> 19 -> 7 -> -5: pair 1 wins set 2
  assert match.sets == [1, 1] and match.set_number == 3
  win_for(0, 24)
  out = win_for(0, 9)  # 31 -> 7 -> -2
  assert out["match_winner"] == 0 and match.winner == 0
  with pytest.raises(ValueError):
    win_for(1, 1)
  js = match.to_json()
  assert js["sets"] == [2, 1] and len(js["deals"]) == 9
  assert js["deals"][0]["contract"] == "Lomt"


def test_exactly_zero_wins_the_set():
  match = m.Match(dealer=3)
  match.need = [3, 31]
  out = match.record([3, -3, 3, -3], "Normal", None, 0)
  assert out["set_winner"] == 0


def test_the_table_gives_bots_the_set_in_game_partnership_order():
  import random as random_lib  # pylint: disable=g-import-not-at-top

  import pyspiel  # pylint: disable=g-import-not-at-top

  from schnaps_web import config  # pylint: disable=g-import-not-at-top
  from schnaps_web import deal as deal_lib  # pylint: disable=g-import-not-at-top
  from schnaps_web import table as table_lib  # pylint: disable=g-import-not-at-top

  game = pyspiel.load_game(deal_lib.GAME_STRING)
  t = table_lib.Table("t", "T", {}, config.Settings(), game, random_lib.Random(0))
  assert t.set_need() is None
  t.match = m.Match(dealer=3)
  t.match.need = [5, 20]  # pair 0 (South-North) needs 5
  # Dealer 3: the Caller is table seat 0 (pair 0), game partnership 0.
  t.deal = deal_lib.Deal(game, 3, random_lib.Random(0))
  assert t.set_need() == (5, 20)
  # Dealer 0: the Caller is table seat 1 (pair 1).
  t.deal = deal_lib.Deal(game, 0, random_lib.Random(0))
  assert t.set_need() == (20, 5)
