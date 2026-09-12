#!/usr/bin/env bash
# Start the HTTP API (Swagger UI on http://localhost:6100/docs).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

cd "$ROOT/suwalski_investing_server"
unset VIRTUAL_ENV
uv run python -m suwalski_investing_server "$@"
