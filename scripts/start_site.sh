#!/bin/bash
# Starts the Schnaps site on 0.0.0.0:8000 (SCHNAPS_WEB_PORT to change) and
# the all-cards watch page on port 8001 (SCHNAPS_WEB_WATCH_PORT; 0 turns it
# off). Loads and compiles the Basic and Large players first (about 30 s
# each), then serves.
. "$(dirname "$0")/env.sh"
cd "$SITE/server"
[ -f "$SITE/client/dist/index.html" ] || echo "warning: client not built (scripts/build_client.sh)"
exec python -m schnaps_web.app
