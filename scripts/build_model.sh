#!/bin/bash
# Assembles models/neural_player/0 from the trained networks in ~ (one time).
set -e
. "$(dirname "$0")/env.sh"
cd "$SITE/server"
python -m schnaps_web.tools.build_player "$@"
