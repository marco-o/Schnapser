"""cardthrowup (docs/cardthrowup.md): Show and Resign.

Resign's scoring in contracts and Normal games, when Resign and Show are
offered, Show opening a hand to the opponents only (and Resign at once for
them), frames before and after a resignation, and the table: both over the
API, bots never throwing and never stalling.
"""

import random
import time

from fastapi import testclient
import pyspiel
import pytest

from schnaps_web import app as app_lib
from schnaps_web import bots as bots_lib
from schnaps_web import config as config_lib
from schnaps_web import deal as deal_lib
from schnaps_web import match
from schnaps_web.game import oracle

PASS, FLECK, FIRST_CALL = 32, 33, 34
CALLS = {"Schnapser": 34, "Lomt": 35, "Bauern": 36}


@pytest.fixture(scope="module")
def game():
  return pyspiel.load_game(deal_lib.GAME_STRING)


def _bid_to_play(game, seed, call=None, fleck=False):
  """A deal in its card play, or None.

  The trump is random; in the bidding the first seat that may call `call`
  calls it (then the next seat flecks if `fleck`), everyone else passes.
  A None `call` passes out to a Normal game.
  """
  rng = random.Random(seed)
  d = deal_lib.Deal(game, seed % 4, rng)
  called = flecked = False
  while not d.is_over and not d.in_play():
    legal = d.state.legal_actions()
    seat = d.to_move()
    if PASS not in legal and FLECK not in legal:
      d.apply(seat, rng.choice(legal))  # the trump choice
      continue
    if call and not called and CALLS[call] in legal:
      a, called = CALLS[call], True
    elif fleck and called and not flecked and FLECK in legal:
      a, flecked = FLECK, True
    else:
      a = PASS if PASS in legal else legal[0]
    d.apply(seat, a)
  if d.is_over or not d.in_play():
    return None
  want = call or "Normal"
  contract = oracle.position(d.state).rules.contract
  if oracle.CONTRACT_NAMES[contract] != want:
    return None
  if fleck and oracle.position(d.state).flecks == 0:
    return None
  return d


def _play_cards(d, rng, tricks, mid=0):
  """Random legal plays until `tricks` are done and `mid` cards are out."""
  while d.in_play():
    p = oracle.position(d.state).play
    if p[6] == tricks and len(p[1]) == mid:
      return True
    if p[6] > tricks:
      return False
    d.apply(d.to_move(), rng.choice(d.state.legal_actions()))
  return False


def _deals(game, call=None, tricks=0, mid=0, fleck=False, n=200, start=0):
  """Deals in the card play at the given trick, from successive seeds."""
  for seed in range(start, start + n):
    d = _bid_to_play(game, seed, call, fleck)
    if d is None:
      continue
    if _play_cards(d, random.Random(seed + 7), tricks, mid):
      yield d


def _winner(d):
  """(winning table pair, points) of a finished deal."""
  return match.deal_winner(d.result()["returns"], d.dealer)


def _seat_of_team(d, team, declarer=False):
  """A table seat of game team `team` (the declarer when asked)."""
  rules = oracle.position(d.state).rules
  if declarer:
    return d.table_seat(rules.declarer)
  return d.table_seat(team)


# -- scoring: resign -----------------------------------------------------------


@pytest.mark.parametrize("call", ["Schnapser", "Lomt", "Bauern"])
def test_resign_in_a_contract(game, call):
  seen = 0
  for fleck in (False, True):
    for d in _deals(game, call, tricks=0, fleck=fleck, n=400):
      pos = oracle.position(d.state)
      stake = oracle.CONTRACT_POINTS[pos.rules.contract] * 2**pos.flecks
      declarer = d.table_seat(pos.rules.declarer)
      declaring_pair = match.pair_of(declarer)
      # The declaring side resigns: the contract fails.
      partner = (declarer + 2) % 4
      d.resign(partner)
      assert _winner(d) == (1 - declaring_pair, stake)
      assert d.result()["throw"]["kind"] == "resign"
      seen += 1
      break
    for d in _deals(game, call, tricks=0, fleck=fleck, n=400, start=500):
      pos = oracle.position(d.state)
      stake = oracle.CONTRACT_POINTS[pos.rules.contract] * 2**pos.flecks
      declarer = d.table_seat(pos.rules.declarer)
      # A defender resigns: the contract is made.
      d.resign((declarer + 1) % 4)
      assert _winner(d) == (match.pair_of(declarer), stake)
      seen += 1
      break
  assert seen == 4


def test_resign_in_a_normal_game_as_if_66(game):
  bases = set()
  for tricks in (2, 3, 4):
    for d in _deals(game, None, tricks=tricks, n=60):
      pos = oracle.position(d.state)
      score, won = pos.play[3], pos.play[4]
      seat = d.to_move()
      team = oracle.team_of(d.game_seat(seat))
      if won[team] == 0:
        base = 3
      elif score[team] < 33:
        base = 2
      else:
        base = 1
      bases.add(base)
      d.resign(seat)
      assert _winner(d) == (1 - match.pair_of(seat), base * 2**pos.flecks)
  assert len(bases) >= 2


# -- when Resign and Show are offered ------------------------------------------


def test_resign_from_the_third_trick_in_a_normal_game(game):
  for tricks, offered in ((0, False), (1, False), (2, True), (3, True)):
    d = next(_deals(game, None, tricks=tricks, n=50))
    for seat in range(4):
      assert d.can_resign(seat) == offered
      assert d.frame(seat)["throws"] == {"resign": offered, "show": True}
    assert d.frame(None)["throws"] == {"resign": False, "show": False}
    if not offered:
      with pytest.raises(deal_lib.DealError):
        d.resign(0)
      assert not d.is_over


def test_resign_during_the_whole_play_of_a_contract(game):
  d = next(_deals(game, "Schnapser", tricks=0, n=400))
  assert all(d.can_resign(s) and d.can_show(s) for s in range(4))
  d = next(_deals(game, "Lomt", tricks=1, mid=2, n=400))
  assert all(d.can_resign(s) for s in range(4))


def test_no_throws_outside_the_card_play(game):
  d = deal_lib.Deal(game, 0, random.Random(5))
  for _ in range(3):  # the trump and some bids
    for seat in range(4):
      assert d.frame(seat)["throws"] == {"resign": False, "show": False}
      with pytest.raises(deal_lib.DealError):
        d.resign(seat)
      with pytest.raises(deal_lib.DealError):
        d.show(seat)
    legal = d.state.legal_actions()
    d.apply(d.to_move(), PASS if PASS in legal else legal[0])


# -- Show ------------------------------------------------------------------------


def _cards(d, viewer, g):
  """Game seat g's cards as table seat `viewer` (None: spectator) sees them."""
  return d.frame(viewer)["presentation"]["view"]["seats"][g]["cards"]


def test_show_opens_the_hand_to_the_opponents_only(game):
  d = next(_deals(game, None, tricks=1, mid=1, n=50))
  shower = d.to_move()
  g = d.game_seat(shower)
  everything = lambda: d.frame(None, reveal=True)["presentation"]["view"]["seats"][g]["cards"]  # noqa: E731
  hand = everything()
  d.show(shower)
  for seat in range(4):
    v = d.frame(seat)["presentation"]["view"]
    me = d.game_seat(seat)
    assert v["shown"] == [g]
    if me == g or me % 2 != g % 2:  # the shower and the two opponents
      assert _cards(d, seat, g) == hand
    else:  # the partner
      assert all(c is None for c in _cards(d, seat, g))
    # Every other hand stays hidden.
    for e in v["seats"]:
      if e["seat"] not in (me, g):
        assert all(c is None for c in e["cards"])
  assert all(c is None for c in _cards(d, None, g))  # spectators
  # Once per deal: the shower is no longer offered Show, the others are.
  assert not d.can_show(shower) and d.frame(shower)["throws"]["show"] is False
  assert all(d.can_show(s) for s in range(4) if s != shower)
  with pytest.raises(deal_lib.DealError):
    d.show(shower)
  # The hand stays open to the opponents as it is played down.
  opponent = (shower + 1) % 4
  rng = random.Random(1)
  for _ in range(4):
    if not d.in_play():
      break
    d.apply(d.to_move(), rng.choice(d.state.legal_actions()))
  if d.in_play():
    assert _cards(d, opponent, g) == everything()
    assert len(everything()) < len(hand)


def test_resign_at_once_when_an_opponent_has_shown(game):
  d = next(_deals(game, None, tricks=0, mid=1, n=50))  # a Normal game's first trick
  shower = d.to_move()
  opponents = ((shower + 1) % 4, (shower + 3) % 4)
  partner = (shower + 2) % 4
  assert not any(d.can_resign(s) for s in range(4))
  d.show(shower)
  assert all(d.can_resign(s) for s in opponents)
  assert not d.can_resign(shower) and not d.can_resign(partner)
  assert d.frame(opponents[0])["throws"]["resign"] is True
  d.resign(opponents[0])
  pos = oracle.position(d.state)
  assert _winner(d)[0] == match.pair_of(shower)
  assert d.result()["throw"] == {
      "kind": "resign",
      "seat": d.game_seat(opponents[0]),
      "trick": pos.play[6],
      "text": "Resign",
  }


# -- frames ----------------------------------------------------------------------


def test_frames_before_and_after_a_resignation(game):
  d = next(_deals(game, None, tricks=2, mid=1, n=50))
  # Before: every viewer sees only its own hand; no throw in the view.
  for seat in range(4):
    f = d.frame(seat)
    me = f["viewer"]["seat"]
    assert f["presentation"]["view"]["throw"] is None
    for entry in f["presentation"]["view"]["seats"]:
      if entry["seat"] != me:
        assert all(c is None for c in entry["cards"])
  spectator = d.frame(None)
  for entry in spectator["presentation"]["view"]["seats"]:
    assert all(c is None for c in entry["cards"])
  thrower = (d.to_move() + 1) % 4  # out of turn is fine
  d.resign(thrower)
  assert d.is_over and d.to_move() is None
  # After: every hand shows to everyone, nobody moves, the deal is over.
  for seat in (None, 0, 1, 2, 3):
    f = d.frame(seat)
    v = f["presentation"]["view"]
    assert v["phase"] == "terminal" and v["toMove"] is None
    assert v["throw"]["kind"] == "resign"
    assert v["throw"]["seat"] == d.game_seat(thrower)
    assert f["presentation"]["actions"] == []
    assert f["throws"] == {"resign": False, "show": False}
    assert f["returns"] == d.result()["returns"]
    cards = [c for e in v["seats"] for c in e["cards"]]
    assert cards and None not in cards
  with pytest.raises(deal_lib.DealError):
    d.apply(d.to_move() or 0, d.state.legal_actions()[0])
  with pytest.raises(deal_lib.DealError):
    d.resign(thrower)
  with pytest.raises(deal_lib.DealError):
    d.show(thrower)


# -- the table and its bots --------------------------------------------------------

FAST = config_lib.Settings(bot_delay=0.0, deal_pause=0.0, client_dir="/nonexistent")


def _h(token):
  return {"X-Seat-Token": token}


def test_show_and_resign_over_the_api_and_the_bots_play_on():
  bots = {"random": bots_lib.RandomBot(seed=3)}
  with testclient.TestClient(app_lib.create_app(FAST, bots)) as client:
    r = client.post("/api/tables", json={"name": "T", "player": "Anna", "seat": 0})
    tid, anna = r.json()["id"], r.json()["token"]
    for seat in (1, 2, 3):
      client.put(f"/api/tables/{tid}/seats/{seat}/bot", json={"bot": "random"}, headers=_h(anna))
    # Nothing to show or throw before the match.
    assert client.post(f"/api/tables/{tid}/show", headers=_h(anna)).status_code == 400
    assert client.post(f"/api/tables/{tid}/throw", json={"kind": "resign"}, headers=_h(anna)).status_code == 400
    assert client.post(f"/api/tables/{tid}/start", headers=_h(anna)).status_code == 200
    assert client.post(f"/api/tables/{tid}/show").status_code == 403
    assert client.post(f"/api/tables/{tid}/throw", json={"kind": "allmine"}, headers=_h(anna)).status_code == 400
    # Anna shows as soon as she may, then resigns when she may (bots may end
    # a deal first: she tries again in the next one).
    deadline = time.time() + 60
    thrown = None
    seen_shown = False
    with client.websocket_connect(f"/ws/tables/{tid}?token={anna}") as ws:
      while time.time() < deadline and thrown is None:
        snap = ws.receive_json()
        frame = snap["frame"]
        if snap["phase"] != "playing" or not frame:
          continue
        me = frame["viewer"]["seat"]
        if me in frame["presentation"]["view"]["shown"]:
          seen_shown = True
        if frame["throws"]["show"]:
          client.post(f"/api/tables/{tid}/show", headers=_h(anna))
          continue
        if frame["throws"]["resign"]:
          r = client.post(f"/api/tables/{tid}/throw", json={"kind": "resign"}, headers=_h(anna))
          if r.status_code == 200:
            thrown = len(snap["match"]["deals"]) + 1
          continue
        actions = frame["presentation"]["actions"]
        if actions:  # Anna's move (the table waits for her)
          ids = [a["id"] for a in actions]
          action = PASS if PASS in ids else ids[0]
          client.post(f"/api/tables/{tid}/actions", json={"action": action}, headers=_h(anna))
      assert thrown is not None and seen_shown
      # The deal is recorded with the throw, and the next deal gets going.
      while time.time() < deadline:
        snap = ws.receive_json()
        if len(snap["match"]["deals"]) >= thrown + 1:
          break
        actions = (snap["frame"] or {}).get("presentation", {}).get("actions")
        if snap["phase"] == "playing" and actions:
          ids = [a["id"] for a in actions]
          action = PASS if PASS in ids else ids[0]
          client.post(f"/api/tables/{tid}/actions", json={"action": action}, headers=_h(anna))
      assert len(snap["match"]["deals"]) >= thrown + 1, "the table stalled"
    t = snap["match"]["deals"][thrown - 1]["throw"]
    assert t == {"kind": "resign", "seat": 0, "text": "Resign"}


def test_bots_never_show_or_resign():
  bots = {"random": bots_lib.RandomBot(seed=4)}
  with testclient.TestClient(app_lib.create_app(FAST, bots)) as client:
    r = client.post("/api/tables", json={"name": "T", "player": "Anna", "seat": 0})
    tid, anna = r.json()["id"], r.json()["token"]
    for seat in range(4):
      client.put(f"/api/tables/{tid}/seats/{seat}/bot", json={"bot": "random"}, headers=_h(anna))
    client.post(f"/api/tables/{tid}/start", headers=_h(anna))
    deadline = time.time() + 120
    while time.time() < deadline:
      t = client.get("/api/tables").json()[0]
      if t["phase"] == "match_over":
        break
      time.sleep(0.05)
    assert t["phase"] == "match_over"
    with client.websocket_connect(f"/ws/tables/{tid}?token={anna}") as ws:
      deals = ws.receive_json()["match"]["deals"]
  assert deals and not any(d["throw"] for d in deals)
