# `just signals <recipe>` — the monthly AI cycle signals job (suwinvtools_server/signals/).
# On the cluster the same command runs as a CronJob (deploy/chart/templates/signals-cronjob.yaml).

set shell := ["bash", "-euo", "pipefail", "-c"]
# Recipes run from the repo root, like the ones in the main justfile.
set working-directory := ".."
set positional-arguments

[private]
default:
    @just --list signals --unsorted

# Ask for the Discord webhooks, SEC identification and the model, write them to .env
init:
    cd suwinvtools_server && env -u VIRTUAL_ENV uv run python -m suwinvtools_server.signals.job init

# One run: read, judge, send what changed. --dry-run stores and sends nothing; --only A1,B4
run *args:
    cd suwinvtools_server && env -u VIRTUAL_ENV uv run python -m suwinvtools_server.signals.job run "$@"

# One check with every verdict and source, e.g. `just signals check A1` — nothing stored or sent
check id:
    cd suwinvtools_server && env -u VIRTUAL_ENV uv run python -m suwinvtools_server.signals.job check "$1"

# A test message on every configured channel
test-discord:
    cd suwinvtools_server && env -u VIRTUAL_ENV uv run python -m suwinvtools_server.signals.job test-discord

# The real outside services (EDGAR, vast.ai, OpenRouter, Google News) — left out of the gate
live-check:
    @./scripts/.internal/live-check.sh
