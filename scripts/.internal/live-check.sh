#!/usr/bin/env bash
# The tests that call the real outside services (`@pytest.mark.live`), which the gate leaves
# out: a service can change its answer without a commit here. The monthly job is the check from
# production's network — a source that changed shape shows up there as INVALID on the status
# channel; this is the same question asked by hand from a laptop.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

cd "$ROOT/suwinvtools_server"
unset VIRTUAL_ENV
exec uv run pytest -m live -o addopts="" "$@"
