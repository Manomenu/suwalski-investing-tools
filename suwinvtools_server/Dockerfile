# Build context is the SOLUTION ROOT, not this directory: the server depends on the
# library through a uv workspace path, so the build needs both projects plus the root
# uv.lock — the only lockfile in the repo.
#
#   podman build -f suwinvtools_server/Dockerfile -t suwalski-server .

FROM docker.io/library/python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Manifests first — this layer is the expensive one and it only rebuilds when a
# dependency moves. Every workspace member's pyproject.toml has to be present or uv
# fails to discover the workspace, including members this image never installs.
COPY pyproject.toml uv.lock ./
COPY suwinvtools_library/pyproject.toml suwinvtools_library/
COPY suwinvtools_server/pyproject.toml suwinvtools_server/
COPY suwinvtools_cli/pyproject.toml suwinvtools_cli/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package suwinvtools-server

# Then the sources, which change every commit.
COPY suwinvtools_library/ suwinvtools_library/
COPY suwinvtools_server/ suwinvtools_server/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package suwinvtools-server


FROM docker.io/library/python:3.14-slim

RUN useradd --system --create-home --uid 10001 app

COPY --from=builder --chown=app:app /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
# The library derives the solution root from its own __file__, which only holds for the
# editable installs used in development. Here it is a wheel under site-packages, so the
# root has to be stated outright or the .env lookup climbs into site-packages.
ENV SUWINVTOOLS_SOLUTION_ROOT=/app
# Ticker snapshots and SEC year history. Not state — everything here is refetchable, so
# losing it costs time rather than data — but the SEC half is expensive enough (3-5 MB a
# company, slow to pull) that the cluster backs this path with a fixed-size disk instead
# of letting it die with the pod. A writable dir owned by the app user is all it needs.
ENV SUWINVTOOLS_MARKET_CACHE=/var/cache/suwalski-market

RUN install -d -o app -g app /var/cache/suwalski-market

USER app
WORKDIR /app
EXPOSE 6100

# Reuses the module entry point the dev script runs, so host and port stay one contract.
CMD ["python", "-m", "suwinvtools_server"]
