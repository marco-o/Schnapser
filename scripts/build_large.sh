#!/bin/bash
# Assembles models/large_player/0 (the Large player): the Basic player's
# forced-contract networks and bidder, with the bigger GPU-trained Normal
# network (step 4 of Docker/gpu-training.md). LARGE_NORMAL picks the
# checkpoint; extra args are passed on, e.g. --overwrite to rebuild.
set -e
. "$(dirname "$0")/env.sh"
cd "$SITE/server"
python -m schnaps_web.tools.build_player --rule set_aware \
  --normal "${LARGE_NORMAL:-$HOME/schnaps_normal_big_gpu@1000}" \
  --part schnapser="$HOME/schnaps_forced_schnapser_r2@500" \
  --out_dir "$SITE/models/large_player" "$@"
