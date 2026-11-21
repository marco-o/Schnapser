#!/bin/bash
# Runs the server tests: test.sh [pytest args]. Without arguments it also
# runs the client's tests (client/src/**/*.test.ts, Node 22 via nvm).
. "$(dirname "$0")/env.sh"
cd "$SITE/server"
python -m pytest -q -p no:cacheprovider "${@:-tests}" 2>&1 | tail -30
status=${PIPESTATUS[0]}
if [ $# -eq 0 ]; then
  echo "--- client tests"
  export NVM_DIR="$HOME/.nvm"
  . "$NVM_DIR/nvm.sh" >/dev/null
  (cd "$SITE/client" && npm test --silent 2>&1 | tail -30; exit "${PIPESTATUS[0]}") || status=1
fi
exit "$status"
