#!/bin/bash
# Runs a Python command in the site's environment, from server/: run_py.sh ARGS...
. "$(dirname "$0")/env.sh"
cd "$SITE/server"
exec python "$@"
