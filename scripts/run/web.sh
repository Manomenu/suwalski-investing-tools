#!/usr/bin/env bash
# Start the web UI on http://localhost:3000. It proxies /api to the server on 6100,
# so run ./scripts/run/server.sh alongside it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

cd "$ROOT/suwalski_investing_web"
[ -d node_modules ] || pnpm install
pnpm dev "$@"
