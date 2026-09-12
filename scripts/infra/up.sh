#!/usr/bin/env bash
# Bring the containerised stack up on http://localhost:8080 — the same two images the
# cluster will run, wired the way the ingress will wire them.
#
#   ./scripts/infra/up.sh             start, reusing cached image layers
#   ./scripts/infra/up.sh --rebuild   rebuild the images from zero first
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

REBUILD=0
for arg in "$@"; do
    case "$arg" in
        --rebuild) REBUILD=1 ;;
        *)
            echo "unknown option: $arg" >&2
            echo "usage: $0 [--rebuild]" >&2
            exit 2
            ;;
    esac
done

cd "$ROOT"

if [ "$REBUILD" -eq 1 ]; then
    # Bypassing the layer cache is the whole point of the flag: a plain build would
    # faithfully reuse the very layer you called this to get rid of.
    echo "==> rebuilding without the layer cache (slow, on purpose)"
    podman compose build --no-cache
fi

echo "==> starting"
podman compose up -d --build

echo
podman compose ps
echo
echo "web   http://localhost:8080"
echo "logs  podman compose logs -f"
