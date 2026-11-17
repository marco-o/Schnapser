#!/bin/bash
# Assembles models/neural_player/0 from the trained networks in ~ (one time).
# The bid rule is set_aware (it uses the set score); extra args are passed on,
# e.g. --overwrite to rebuild. The Schnapser part is the round-2 network,
# retrained for the rule that the defenders' first trick ends the deal.
set -e
. "$(dirname "$0")/env.sh"
cd "$SITE/server"
python -m schnaps_web.tools.build_player --rule set_aware \
  --part schnapser="$HOME/schnaps_forced_schnapser_r2@500" "$@"
