#!/usr/bin/env bash
# Stop the containerised stack. Images stay on disk; `up.sh --rebuild` is what replaces them.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

cd "$ROOT"
podman compose down --remove-orphans
