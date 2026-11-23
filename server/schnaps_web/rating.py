"""Pair ratings: Elo for the two pairs of a set (pure, no storage).

A pair is two players, whatever their seats. Each player is an identity:

  "u:<username>"  a registered user (lower-case username)
  "b:<kind>"      a bot by its kind, the catalog key ("b:basic", "b:large",
                  "b:2a"), not by the name it got at the table ("Hermione")
                  nor by its label ("Bologna"), so renaming a bot keeps
                  its ratings

A guest (a nickname without an account) has no identity, so a set with a
guest in it is not rated.

A pair's key is its two identities, sorted, joined by "+": "b:basic+u:anna".
The same two players are the same pair, whichever seats they take.

Every pair starts at START (600). After a set the winners gain, and the
losers drop, K * (1 - E), where E = 1 / (1 + 10 ** ((R_loser - R_winner) /
SCALE)) is the winners' expected score: an upset moves more points than an
expected win.
"""

from typing import Optional, Sequence

START = 600.0
K = 32.0
SCALE = 400.0

USER = "u:"
BOT = "b:"

#: What each bot kind is called on the site (bots.py takes its labels from
#: here). A kind missing here shows as itself.
BOT_LABELS = {
    "basic": "Bologna", "large": "Firenze", "2a": "Verona", "napoli": "Napoli",
}


def user_id(username: str) -> str:
  """A registered user's identity."""
  return USER + username.lower()


def bot_id(kind: str) -> str:
  """A bot's identity, by its kind ("basic")."""
  return BOT + kind


def bot_label(kind: str) -> str:
  """What the site calls bot kind `kind` ("Bologna")."""
  return BOT_LABELS.get(kind, kind)


def pair_key(a: str, b: str) -> str:
  """The key of the pair of identities a and b (order does not matter)."""
  return "+".join(sorted((a, b)))


def members(key: str) -> list[str]:
  """The two identities of a pair key."""
  return key.split("+")


def lineup_pairs(lineup: Sequence[Optional[str]]) -> Optional[tuple[str, str]]:
  """The keys of pair 0 (seats 0, 2) and pair 1 (seats 1, 3).

  None when a seat has no identity (empty, or a guest).
  """
  if len(lineup) != 4 or any(i is None for i in lineup):
    return None
  return pair_key(lineup[0], lineup[2]), pair_key(lineup[1], lineup[3])


def expected(rating: float, other: float) -> float:
  """The expected score (0..1) of a pair rated `rating` against `other`."""
  return 1.0 / (1.0 + 10.0 ** ((other - rating) / SCALE))


def update(winner: float, loser: float, k: float = K) -> tuple[float, float]:
  """The new (winner, loser) ratings after one set."""
  delta = k * (1.0 - expected(winner, loser))
  return winner + delta, loser - delta
