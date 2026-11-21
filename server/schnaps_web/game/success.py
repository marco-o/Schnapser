"""How often a called contract succeeds, from the pre-computed table.

success_table.json (scripts/build_success_table.py) holds, per contract,
hand class and declarer game seat, the chance the declarer's pair makes the
contract. Classes follow open_spiel's envs/schnaps_forced.py: the hand's
four suit rank masks (bit r = rank r, Unter..As), trump first for Schnapser
and Bauern, the other suits in descending order.
"""

import functools
import json
import os
from typing import Optional, Sequence

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "success_table.json")
_NUM_RANKS = 5


@functools.lru_cache(maxsize=1)
def _table() -> dict:
  try:
    with open(_PATH) as f:
      return json.load(f)["contracts"]
  except FileNotFoundError:
    return {}


def class_key(cards: Sequence[int], trump: Optional[int], trump_marked: bool) -> str:
  """The hand's class key, as the table spells it ("m0,m1,m2,m3")."""
  masks = [0, 0, 0, 0]
  for c in cards:
    masks[c // _NUM_RANKS] |= 1 << (c % _NUM_RANKS)
  if trump_marked and trump is not None:
    rest = sorted((masks[s] for s in range(4) if s != trump), reverse=True)
    key = [masks[trump], *rest]
  else:
    key = sorted(masks, reverse=True)
  return ",".join(str(m) for m in key)


def chance(
    contract: str, cards: Sequence[int], trump: Optional[int], seat: int
) -> Optional[float]:
  """The chance `seat` (a game seat) makes `contract` with `cards`, or None.

  None when the contract has no table (Jodler, Hermort) or the class is not
  in it (a hopeless hand).
  """
  entry = _table().get(contract)
  if entry is None or len(cards) != 5:
    return None
  row = entry["chance"].get(class_key(cards, trump, entry["trumpMarked"]))
  return None if row is None else row[seat]
