#!/bin/bash
# Builds the browser client into client/dist (needs Node 22: scripts/install.sh).
set -e
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
cd "$(dirname "$0")/../client"
[ -d node_modules ] || npm install --no-audit --no-fund
npm run build
