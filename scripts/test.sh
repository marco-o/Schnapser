#!/bin/bash
# Runs the server tests: test.sh [pytest args]
. "$(dirname "$0")/env.sh"
cd "$SITE/server"
python -m pytest -q -p no:cacheprovider "${@:-tests}" 2>&1 | tail -30
