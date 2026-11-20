#!/bin/bash
# Starts the Schnaps site on 0.0.0.0:8000 (SCHNAPS_WEB_PORT to change).
# Loads and compiles the Basic and Large players first (about 30 s each),
# then serves.
. "$(dirname "$0")/env.sh"
cd "$SITE/server"
[ -f "$SITE/client/dist/index.html" ] || echo "warning: client not built (scripts/build_client.sh)"
exec uvicorn --factory schnaps_web.app:create_app \
  --host "${SCHNAPS_WEB_HOST:-0.0.0.0}" --port "${SCHNAPS_WEB_PORT:-8000}" \
  --log-level warning
