"""cardthrowup (docs/cardthrowup.md): Resign and Allmine.

Scoring of every row of the design's table, claims refused and accepted
(a Lomt claimed before the first lead), when Resign is offered, frames
before and after a throw, the claim solver against brute force, and the
table: a throw over the API, bots claiming and never stalling.
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


# -- when Resign and Allmine are offered ---------------------------------------


def test_resign_from_the_third_trick_in_a_normal_game(game):
  for tricks, offered in ((0, False), (1, False), (2, True), (3, True)):
    d = next(_deals(game, None, tricks=tricks, n=50))
    for seat in range(4):
      assert d.can_resign(seat) == offered
      assert d.frame(seat)["throws"] == {"resign": offered, "allmine": True}
    assert d.frame(None)["throws"] == {"resign": False, "allmine": False}
    if not offered:
      with pytest.raises(deal_lib.DealError):
        d.resign(0)
      assert not d.is_over


def test_resign_during_the_whole_play_of_a_contract(game):
  d = next(_deals(game, "Schnapser", tricks=0, n=400))
  assert all(d.can_resign(s) and d.can_claim(s) for s in range(4))
  d = next(_deals(game, "Lomt", tricks=1, mid=2, n=400))
  assert all(d.can_resign(s) for s in range(4))


def test_no_throws_outside_the_card_play(game):
  d = deal_lib.Deal(game, 0, random.Random(5))
  for _ in range(3):  # the trump and some bids
    for seat in range(4):
      assert d.frame(seat)["throws"] == {"resign": False, "allmine": False}
      with pytest.raises(deal_lib.DealError):
        d.resign(seat)
      with pytest.raises(deal_lib.DealError):
        d.claim(seat)
    legal = d.state.legal_actions()
    d.apply(d.to_move(), PASS if PASS in legal else legal[0])


# -- Allmine ----------------------------------------------------------------------


def test_allmine_accepted_in_a_normal_game_is_played_out(game):
  accepted = 0
  for tricks in (1, 2, 3, 4):
    for d in _deals(game, None, tricks=tricks, n=80):
      pos = oracle.position(d.state)
      seat = d.to_move()
      team = oracle.team_of(d.game_seat(seat))
      value = oracle.ClaimSolver(pos.rules, team).value(pos.play)
      if value <= 0:
        continue
      assert d.claim_holds(seat)
      assert d.claim(seat) == "Allmine"
      t = d.result()["throw"]
      assert t["kind"] == "allmine" and t["accepted"] and t["reason"] is None
      # The claimant's side wins what the solver's line scores.
      assert _winner(d) == (match.pair_of(seat), value * 2**pos.flecks)
      assert 1 <= value <= 3
      accepted += 1
  assert accepted >= 5


def test_a_wrong_allmine_counts_as_a_resignation(game):
  refused = 0
  for tricks in (0, 1, 2, 3):
    for d in _deals(game, None, tricks=tricks, n=60):
      pos = oracle.position(d.state)
      seat = d.to_move()
      team = oracle.team_of(d.game_seat(seat))
      if oracle.ClaimSolver(pos.rules, team).value(pos.play) != oracle.LOST:
        continue
      before = d.frame(None, reveal=True)["presentation"]["view"]["seats"]
      expected = deal_lib._resign_returns(pos, d.game_seat(seat))  # pylint: disable=protected-access
      assert not d.claim_holds(seat)
      assert d.claim(seat) == "Allmine refused"
      t = d.result()["throw"]
      assert t["accepted"] is False
      assert d.result()["returns"] == list(expected)
      # The reason: an opponent's card that takes a trick, from their hand.
      reason = t["reason"]
      assert oracle.team_of(reason["seat"]) != team
      assert reason["card"] in before[reason["seat"]]["cards"]
      assert reason["cardName"].split()[0] in ("Herz", "Caro", "Pik", "Kreuz")
      assert _winner(d)[0] == 1 - match.pair_of(seat)
      refused += 1
  assert refused >= 5


def test_a_lomt_claimed_before_the_first_lead(game):
  declarer_claims = defender_claims = 0
  for d in _deals(game, "Lomt", tricks=0, n=1500):
    pos = oracle.position(d.state)
    declarer = pos.rules.declarer
    team = oracle.team_of(declarer)
    stake = 9 * 2**pos.flecks
    if oracle.ClaimSolver(pos.rules, team).value(pos.play) > 0:
      seat = d.table_seat(declarer)
      assert d.claim(seat) == "Allmine"
      assert _winner(d) == (match.pair_of(seat), stake)
      declarer_claims += 1
    elif oracle.ClaimSolver(pos.rules, 1 - team).value(pos.play) > 0:
      seat = d.table_seat((declarer + 1) % 4)
      assert d.claim(seat) == "Allmine"
      assert _winner(d) == (match.pair_of(seat), stake)  # the Lomt fails
      defender_claims += 1
    if declarer_claims >= 2 and defender_claims >= 2:
      break
  assert declarer_claims >= 1 and defender_claims >= 1


def test_claim_solver_matches_brute_force(game):
  def brute(rules, team, p):
    """Can `team` take every remaining trick and win? (no pruning)"""
    outcomes = []
    for a in oracle.play_legal(rules, p):
      q, v = oracle.play_apply(rules, p, a)
      if len(p[1]) == 3 and oracle.team_of(q[2]) != team:
        outcomes.append(False)
      elif v is not None:
        outcomes.append((v if team == 0 else -v) > 0)
      else:
        outcomes.append(brute(rules, team, q))
    mine = oracle.team_of(oracle.to_move(p)) == team
    return any(outcomes) if mine else all(outcomes)

  checked = 0
  for call in (None, "Schnapser", "Lomt", "Bauern"):
    for d in _deals(game, call, tricks=2, mid=1, n=60):
      pos = oracle.position(d.state)
      for team in (0, 1):
        solver = oracle.ClaimSolver(pos.rules, team)
        got = solver.value(pos.play) > 0
        assert got == brute(pos.rules, team, pos.play)
        assert oracle.ClaimSolver(pos.rules, team).holds(pos.play) == got
        checked += 1
  assert checked > 50


def test_bot_check_gives_up_over_its_budget(game):
  d = next(_deals(game, None, tricks=0, n=50))
  pos = oracle.position(d.state)
  with pytest.raises(oracle.Budget):
    oracle.ClaimSolver(pos.rules, 0, budget=1).holds(pos.play)
  assert d.claim_holds(d.to_move(), budget=1) is False


# -- frames ----------------------------------------------------------------------


def test_frames_before_and_after_a_throw(game):
  for kind in ("resign", "allmine"):
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
    getattr(d, "resign" if kind == "resign" else "claim")(thrower)
    assert d.is_over and d.to_move() is None
    # After: every hand shows to everyone, nobody moves, the deal is over.
    for seat in (None, 0, 1, 2, 3):
      f = d.frame(seat)
      v = f["presentation"]["view"]
      assert v["phase"] == "terminal" and v["toMove"] is None
      assert v["throw"]["kind"] == kind
      assert v["throw"]["seat"] == d.game_seat(thrower)
      assert f["presentation"]["actions"] == []
      assert f["throws"] == {"resign": False, "allmine": False}
      assert f["returns"] == d.result()["returns"]
      cards = [c for e in v["seats"] for c in e["cards"]]
      assert cards and None not in cards
    with pytest.raises(deal_lib.DealError):
      d.apply(d.to_move() or 0, d.state.legal_actions()[0])
    with pytest.raises(deal_lib.DealError):
      d.resign(thrower)
    with pytest.raises(deal_lib.DealError):
      d.claim(thrower)


# -- the table and its bots --------------------------------------------------------

FAST = config_lib.Settings(bot_delay=0.0, deal_pause=0.0, client_dir="/nonexistent")


def _h(token):
  return {"X-Seat-Token": token}


def test_a_throw_over_the_api_and_the_bots_play_on():
  bots = {"random": bots_lib.RandomBot(seed=3)}
  with testclient.TestClient(app_lib.create_app(FAST, bots)) as client:
    r = client.post("/api/tables", json={"name": "T", "player": "Anna", "seat": 0})
    tid, anna = r.json()["id"], r.json()["token"]
    for seat in (1, 2, 3):
      client.put(f"/api/tables/{tid}/seats/{seat}/bot", json={"bot": "random"}, headers=_h(anna))
    # Nothing to throw before the match.
    assert client.post(f"/api/tables/{tid}/throw", json={"kind": "resign"}, headers=_h(anna)).status_code == 400
    assert client.post(f"/api/tables/{tid}/start", headers=_h(anna)).status_code == 200
    assert client.post(f"/api/tables/{tid}/throw", json={"kind": "allmine"}).status_code == 403
    assert client.post(f"/api/tables/{tid}/throw", json={"kind": "nope"}, headers=_h(anna)).status_code == 400
    # Anna claims as soon as she may (bots may end a deal first: retry).
    deadline = time.time() + 60
    thrown = None
    with client.websocket_connect(f"/ws/tables/{tid}?token={anna}") as ws:
      while time.time() < deadline and thrown is None:
        snap = ws.receive_json()
        frame = snap["frame"]
        if snap["phase"] != "playing" or not frame:
          continue
        if not frame["throws"]["allmine"]:
          actions = frame["presentation"]["actions"]
          if actions:  # Anna's bid (the table waits for her)
            ids = [a["id"] for a in actions]
            action = PASS if PASS in ids else ids[0]
            client.post(f"/api/tables/{tid}/actions", json={"action": action}, headers=_h(anna))
          continue
        r = client.post(f"/api/tables/{tid}/throw", json={"kind": "allmine"}, headers=_h(anna))
        if r.status_code == 200:
          thrown = len(snap["match"]["deals"]) + 1
      assert thrown is not None
      # The deal is recorded with the throw, and the next deal gets going.
      # (Anna passes or plays when the table waits for her.)
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
    assert t["kind"] == "allmine" and t["seat"] == 0 and t["text"].startswith("Allmine")


def test_bots_claim_and_never_resign():
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
  throws = [d["throw"] for d in deals if d["throw"]]
  assert throws, "no bot ever claimed"
  # A bot claims only what the solver proves: never refused, never resign.
  assert all(t["kind"] == "allmine" and t["accepted"] for t in throws)
