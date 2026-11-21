"""Writes the success table the bid buttons show (game/success_table.json).

  python3 scripts/build_success_table.py \
      ~/schnaps_forced_measure_lomt.json ~/schnaps_forced_measure_bauern.json \
      ~/schnaps_forced_measure_schnapser_r2.json

Reads round-2 measurements (open_spiel examples/schnaps_forced_measure.py:
each contract's network played every kept hand class from every declarer
seat) and keeps, per (hand class, declarer game seat), the chance the
declarer's pair makes the contract as the network's value head predicted it
at the first play: p = (mean value / points + 1) / 2. The value head is the
best-calibrated predictor of real success (Docker/forced-contract-option.md,
"Round 2 results"); the measured win rates rest on as few as 12 deals per
cell for Schnapser.

A class is the hand's four suit rank masks (bit r = rank r held, ranks
Unter..As), trump first for Schnapser and Bauern, the other suits in
descending order (envs/schnaps_forced.py, class_key). Classes the
measurement left out (hopeless hands) are missing: no hint.

Plain Python, no dependencies.
"""

import json
import os
import sys

OUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "server", "schnaps_web", "game", "success_table.json",
)
NAMES = {"schnapser": "Schnapser", "lomt": "Lomt", "bauern": "Bauern"}


def main(paths):
  contracts = {}
  for path in paths:
    with open(os.path.expanduser(path)) as f:
      res = json.load(f)
    name = NAMES[res["contract"]]
    points = float(res["points"])
    table = {}
    for i, key in enumerate(res["classes"]):
      row = []
      for seat in range(4):
        n = res["n"][i][seat]
        if not n:
          row.append(None)
          continue
        p = (res["value_sum"][i][seat] / n / points + 1) / 2
        row.append(round(min(max(p, 0.0), 1.0), 3))
      if any(p is not None for p in row):
        table[",".join(str(int(m)) for m in key)] = row
    contracts[name] = {
        "trumpMarked": name != "Lomt",
        "checkpoint": res["checkpoint"],
        "chance": table,
    }
    print(f"{name}: {len(table)} classes from {res['checkpoint']}")
  with open(OUT, "w") as f:
    json.dump({"schema": "schnaps-web-success/1", "contracts": contracts}, f,
              separators=(",", ":"))
  print(f"wrote {os.path.normpath(OUT)}")


if __name__ == "__main__":
  if len(sys.argv) < 2:
    sys.exit(__doc__)
  main(sys.argv[1:])
