# Sourced by the other scripts: the open_spiel venv and import paths (WSL).
SITE=/mnt/c/Users/marco/Documents/git/Docker/schnaps-web
OPEN_SPIEL=/mnt/c/Users/marco/Documents/git/Docker/open_spiel
. "$OPEN_SPIEL/venv/bin/activate"
export PYTHONPATH="$SITE/server:$OPEN_SPIEL:$OPEN_SPIEL/build/python"
export JAX_PLATFORMS=cpu
