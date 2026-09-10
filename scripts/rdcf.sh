#!/usr/bin/env bash
# Run the reverse-DCF calculator in the terminal. All arguments go straight to the CLI:
#   ./scripts/rdcf.sh --price 224.03 --shares 24.40 --fcf 127.01 --fcf-margin 42% \
#       --optimized-margin 35% --growth 1-3:55% --discount 10% --terminal 3%
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT/suwalski_investing_cli"
unset VIRTUAL_ENV
uv run rdcf "$@"
