"""Writes the played-results table the bidders read.

  python3 scripts/build_played_table.py [data/played_success.json]

Reads scripts/sample_success.py's data (deals the Basic bot played out with
forced bidding) and keeps the indexes a bidder consults for its own bids
(bidding.py, "Played results"):

  normal             every (mask, seat): the seat's pair wins the Normal game
  schnapser_caller   seat 0: the Caller makes the Schnapser it called
  schnapser_partner  seat 2: the Caller's partner makes its Schnapser
  lomt               seat 0 (any declarer: the declarer leads)
  bauern             the declarer's seat, hands holding the trump As only

Each game keeps parallel lists "keys", "n", "wins", sorted by key, where
key = (((m0 * 32 + m1) * 32 + m2) * 32 + m3) * 4 + seat and m0..m3 are the
hand's class key (game/success.py class_key: the suit rank masks, trump
first except in Lomt, the others descending).

Writes server/schnaps_web/game/played_table.json and, when the open_spiel
tree sits beside schnaps-web, its copy
open_spiel/open_spiel/python/scale/envs/schnaps_played_table.json.

Plain Python, no dependencies.
"""

import json
import os
import sys
import time

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(SITE, "data", "played_success.json")
OUTS = (
    os.path.join(SITE, "server", "schnaps_web", "game", "played_table.json"),
    os.path.join(os.path.dirname(SITE), "open_spiel", "open_spiel", "python",
                 "scale", "envs", "schnaps_played_table.json"),
)
SCHEMA = "schnaps-played-table/1"
TRUMP_AS = 1 << 4  # the As bit of the trump mask


def keep(game, masks, seat):
  if game == "schnapser_caller":
    return seat == 0
  if game == "schnapser_partner":
    return seat == 2
  if game == "bauern":
    return bool(masks[0] & TRUMP_AS)
  return True


def main(path):
  with open(path) as f:
    data = json.load(f)
  games = {}
  for game, table in data["games"].items():
    rows = []
    for index, (n, wins) in table.items():
      mask, seat = index.split("@")
      masks = [int(m) for m in mask.split(",")]
      seat = int(seat)
      if n and keep(game, masks, seat):
        key = (((masks[0] * 32 + masks[1]) * 32 + masks[2]) * 32 + masks[3]) * 4 + seat
        rows.append((key, n, wins))
    rows.sort()
    games[game] = {
        "keys": [r[0] for r in rows],
        "n": [r[1] for r in rows],
        "wins": [r[2] for r in rows],
    }
    print(f"{game}: {len(rows)} indexes, {sum(r[1] for r in rows)} samples")
  out = {
      "schema": SCHEMA,
      "source": {
          "data": os.path.basename(path),
          "bot": data.get("bot"),
          "games_played": sum(r["games"] for r in data["runs"]),
          "runs": [{"target": r["target"], "games": r["games"]} for r in data["runs"]],
          "built": time.strftime("%Y-%m-%d %H:%M:%S"),
      },
      "games": games,
  }
  for dest in OUTS:
    if not os.path.isdir(os.path.dirname(dest)):
      print(f"skipped {dest} (no such directory)")
      continue
    with open(dest, "w") as f:
      json.dump(out, f, separators=(",", ":"))
    print(f"wrote {os.path.normpath(dest)}")


if __name__ == "__main__":
  main(sys.argv[1] if len(sys.argv) > 1 else DATA)
