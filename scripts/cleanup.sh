#!/usr/bin/env bash
# Remove what working on this repo leaves behind — inside it and outside it.
#
# Layers, because they are not equally expensive to rebuild:
#   (default)   caches and generated files inside the repo — free to recreate
#   --venvs     the three .venv directories        — `uv sync` rebuilds them
#   --system    traces outside the repo: pytest's /tmp dirs, yfinance's timezone
#               cache, this repo's VS Code workspace storage, and the shared uv cache
#   --all       all of the above
#
# Nothing here touches /var: uv, pytest and yfinance all follow XDG and write to
# ~/.cache and /tmp. Anything under /var/tmp on this machine belongs to the system,
# not to us, so this script leaves it alone.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

DRY_RUN=0
DO_VENVS=0
DO_SYSTEM=0
ASSUME_YES=0

usage() {
    sed -n '2,13p' "$0" | sed 's/^# \?//'
    echo
    echo "usage: $(basename "$0") [--venvs] [--system] [--all] [--dry-run] [--yes]"
}

for arg in "$@"; do
    case "$arg" in
        --dry-run|-n) DRY_RUN=1 ;;
        --venvs) DO_VENVS=1 ;;
        --system) DO_SYSTEM=1 ;;
        --all) DO_VENVS=1; DO_SYSTEM=1 ;;
        --yes|-y) ASSUME_YES=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $arg"; usage; exit 1 ;;
    esac
done

FREED_KB=0

size_kb() {
    du -sk "$1" 2>/dev/null | cut -f1 || echo 0
}

human() {
    numfmt --to=iec --suffix=B --format='%.1f' $(( $1 * 1024 )) 2>/dev/null || echo "${1}K"
}

# Deletes one path, but only inside a directory we are allowed to touch.
drop() {
    local path="$1" label="$2" guard="$3"
    [[ -e "$path" ]] || return 0
    case "$path" in
        "$guard"/*) ;;
        *) echo "  REFUSED  $path is outside $guard"; return 0 ;;
    esac

    local kb; kb="$(size_kb "$path")"
    FREED_KB=$(( FREED_KB + kb ))
    if [[ $DRY_RUN -eq 1 ]]; then
        printf '  would remove  %-52s %s\n' "$label" "$(human "$kb")"
    else
        rm -rf "$path"
        printf '  removed       %-52s %s\n' "$label" "$(human "$kb")"
    fi
}

confirm() {
    [[ $DRY_RUN -eq 1 || $ASSUME_YES -eq 1 ]] && return 0
    [[ -t 0 ]] || { echo "  not a terminal — rerun with --yes to confirm"; return 1; }
    read -r -p "  $1 [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]]
}

echo "== inside the repo =="
while IFS= read -r path; do
    drop "$path" "${path#"$ROOT"/}" "$ROOT"
done < <(find "$ROOT" -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache -o -name .mypy_cache \) -not -path '*/.venv/*' 2>/dev/null)

drop "$ROOT/.coverage" ".coverage" "$ROOT"
# Cached ticker snapshots — refetched on the next --ticker run.
while IFS= read -r path; do
    drop "$path" "${path#"$ROOT"/}" "$ROOT"
done < <(find "$ROOT/.artifacts" -mindepth 1 -maxdepth 1 -not -name .gitkeep 2>/dev/null)

if [[ $DO_VENVS -eq 1 ]]; then
    echo
    echo "== virtualenvs (rebuild with: uv sync) =="
    while IFS= read -r path; do
        drop "$path" "${path#"$ROOT"/}" "$ROOT"
    done < <(find "$ROOT" -maxdepth 2 -type d -name .venv 2>/dev/null)
fi

if [[ $DO_SYSTEM -eq 1 ]]; then
    echo
    echo "== outside the repo =="

    # pytest's tmp_path dirs. Shared with every other project's test run on this
    # machine, so it is called out rather than swept in silently.
    pytest_tmp="${TMPDIR:-/tmp}/pytest-of-$USER"
    if [[ -d "$pytest_tmp" ]]; then
        if confirm "remove $pytest_tmp ($(human "$(size_kb "$pytest_tmp")")) — includes other projects' test runs?"; then
            drop "$pytest_tmp" "$pytest_tmp" "${TMPDIR:-/tmp}"
        else
            echo "  kept          $pytest_tmp"
        fi
    fi

    # yfinance writes a timezone cache the first time a ticker is fetched.
    drop "$HOME/.cache/py-yfinance" "~/.cache/py-yfinance (yfinance timezone cache)" "$HOME/.cache"

    # VS Code keeps per-workspace state; only the entries pointing at this repo go.
    storage="$HOME/.config/Code/User/workspaceStorage"
    if [[ -d "$storage" ]]; then
        for dir in "$storage"/*/; do
            [[ -f "${dir}workspace.json" ]] || continue
            grep -Fq "$ROOT" "${dir}workspace.json" 2>/dev/null || continue
            drop "${dir%/}" "~/.config/Code/User/workspaceStorage/$(basename "${dir%/}")" "$storage"
        done
    fi

    # The uv cache is shared by every uv project on this machine; prune only drops
    # entries nothing references any more, so it never breaks another project.
    if command -v uv >/dev/null 2>&1; then
        if [[ $DRY_RUN -eq 1 ]]; then
            echo "  would run     uv cache prune (shared cache, removes unreferenced entries only)"
        elif confirm "run 'uv cache prune' on the shared cache ($(human "$(size_kb "$HOME/.cache/uv")"))?"; then
            uv cache prune >/dev/null 2>&1 && echo "  pruned        ~/.cache/uv"
        else
            echo "  kept          ~/.cache/uv"
        fi
    fi
fi

echo
if [[ $DRY_RUN -eq 1 ]]; then
    echo "dry run — nothing was deleted. $(human "$FREED_KB") would be freed."
else
    echo "freed $(human "$FREED_KB")."
fi
