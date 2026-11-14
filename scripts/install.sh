#!/bin/bash
# One-time setup in WSL Ubuntu: Node 22 (nvm, user level) for the client
# build, and the web server's Python packages in the open_spiel venv.
set -e
export NVM_DIR="$HOME/.nvm"
if [ ! -s "$NVM_DIR/nvm.sh" ]; then
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
fi
. "$NVM_DIR/nvm.sh"
nvm install 22
node --version
VENV=/mnt/c/Users/marco/Documents/git/Docker/open_spiel/venv
"$VENV/bin/pip" install "fastapi>=0.115" "uvicorn[standard]>=0.32" httpx
