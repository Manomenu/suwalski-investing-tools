#!/usr/bin/env bash
# Lint + test the whole solution and print a summary report.
# Exit code is non-zero if any step failed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PYTHON_PROJECTS=(suwalski_investing_library suwalski_investing_server suwalski_investing_cli)

declare -a REPORT
FAILED=0

run_step() {
    local name="$1"; shift
    echo
    echo "==> $name"
    if "$@"; then
        REPORT+=("PASS  $name")
    else
        REPORT+=("FAIL  $name")
        FAILED=1
    fi
}

lint() {
    (cd "$ROOT" && uvx ruff check .)
}

format_check() {
    # Does not rewrite anything — run `uvx ruff format .` yourself if this fails.
    (cd "$ROOT" && uvx ruff format --check .)
}

web_typecheck() {
    cd "$ROOT/suwalski_investing_web"
    [ -d node_modules ] || pnpm install --silent
    pnpm exec tsc --noEmit
}

helm_chart() {
    # `lint` łapie błędy składni, ale przechodzi nawet wtedy, gdy szablon nigdy nie
    # wyrenderuje się poprawnie. `template` faktycznie go składa — i to on wyłapie
    # brakujące pole albo złe wcięcie. Tag podajemy zmyślony, bo tu sprawdzamy kształt,
    # a nie to, czy obraz istnieje.
    cd "$ROOT"
    helm lint deploy/chart --set image.tag=sha-lint --quiet
    helm template lint-check deploy/chart --set image.tag=sha-lint >/dev/null
}

pytest_project() {
    local project="$1"
    if [ ! -d "$ROOT/$project/tests" ]; then
        echo "(no tests)"
        return 0
    fi
    (cd "$ROOT/$project" && unset VIRTUAL_ENV && uv run pytest)
}

run_step "lint (ruff)" lint
run_step "format (ruff format --check)" format_check
for project in "${PYTHON_PROJECTS[@]}"; do
    run_step "pytest $project" pytest_project "$project"
done
run_step "typecheck suwalski_investing_web (tsc)" web_typecheck

# helm bywa nieobecny na świeżej maszynie. Pomijamy z wyraźną adnotacją zamiast raportować
# PASS — cicho pominięty krok jest gorszy niż brak kroku.
if command -v helm >/dev/null 2>&1; then
    run_step "helm chart (lint + template)" helm_chart
else
    REPORT+=("SKIP  helm chart — brak helm (jest w ~/.dotfiles/fedora/nix/home.nix)")
fi

echo
echo "================ test-solution report ================"
for line in "${REPORT[@]}"; do
    echo "  $line"
done
echo "======================================================"
exit "$FAILED"
