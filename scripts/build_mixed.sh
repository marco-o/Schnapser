#!/bin/bash
# Assembles models/mixed_player/0 (the 2a player): the site's bidder with ONE
# network that plays every contract (step 2a, Docker/step2a-options.md).
# MIXED_NET picks the checkpoint; extra args are passed on, e.g. --overwrite
# to rebuild.
set -e
. "$(dirname "$0")/env.sh"
cd "$SITE/server"
python -m schnaps_web.tools.build_one \
  "${MIXED_NET:-$HOME/schnaps_mixed_big_gpu@500}" \
  --step 0 --out_dir "$SITE/models/mixed_player" "$@"
