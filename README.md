# suwalski-investing-tools

Homelab toolkit for equity valuation. First tool: a **reverse DCF with split growth** —
you pin the growth you actually have a view on (say "55% for the next 3 years"), and the
model solves what the remaining years must compound at for the intrinsic value to equal
today's price. That solved number is the question worth arguing about: *is that growth
plausible?*

```
GROWTH THE PRICE REQUIRES
  years 1-3    55.00%   your input
  years 4-10    4.76%   <- solved

  implied revenue CAGR over 10 years: 17.83%
  at that path intrinsic value is 224.03 against a 224.03 price
```

## Layout

| Project | What it is |
| --- | --- |
| `suwalski_investing_library/` | The valuation engine, the pydantic contracts, and `marketdata/` (ticker snapshots off Yahoo Finance). The engine half is stdlib + pydantic only — importing it pulls in no scraper. |
| `suwalski_investing_server/` | FastAPI over the engine. Exists so a browser dashboard can call it later. Port 6100. |
| `suwalski_investing_cli/` | `rdcf` — the same engine in the terminal, for fast iteration without a UI. |
| `scripts/` | Entry points: run the server, run the CLI, lint+test everything. |
| `infrastructure/` | Kubernetes / Terraform, once there is something worth deploying. See its README. |
| `.artifacts/` | Local scratch: cached ticker snapshots. Gitignored. |
| `docs/` | `reverse-dcf.md` (the model and its math), `guidelines.md` (repo rules). |

Prerequisite: [uv](https://docs.astral.sh/uv/). Each project is its own uv project with a
committed lockfile; the server and CLI depend on `suwalski-investing-library[tickers]` as an
editable path dependency. The `tickers` extra is what drags in `yfinance` — the library
installed without it is pure valuation math.

## Run it

Terminal (no server needed). With a ticker, the observable facts are read off Yahoo
Finance and only the assumptions stay on the command line:

```bash
./scripts/rdcf.sh --ticker NVDA --optimized-margin 35% --growth 1-3:55% \
    --discount 10% --terminal 3%
```

```
NVDA  price 223.67 USD  shares 24.15B  market cap 5.40T
  revenue TTM 302.97B   FCF TTM 127.01B (41.9%)   net debt -24.12B
  [yfinance, fetched just now]
```

Every fetched value can be overridden by passing the flag explicitly, and the whole thing
works with no ticker at all:

```bash
./scripts/rdcf.sh --price 224.03 --shares 24.40 \
    --fcf 127.01 --fcf-margin 42% --optimized-margin 35% \
    --growth 1-3:55% --discount 10% --terminal 3%
```

Snapshots are cached for 15 minutes under `.artifacts/market/` — `--refresh` forces a
refetch, `--cache-ttl` changes the window. Exit codes: `1` the price cannot be solved,
`2` bad inputs, `3` the market data lookup failed.

Rates take `55%` or `0.55` — a bare number is always a decimal fraction. `--growth` is
repeatable and takes `YEARS:RATE` (`1-3:55%`, or `5:10%` for a single year); every year no
segment covers is handed to the solver. Add `--json` for the raw result.

HTTP API:

```bash
./scripts/run-server.sh          # Swagger UI at http://localhost:6100/docs

# facts for the form
curl -s localhost:6100/market/NVDA | jq '{price, shares_outstanding, revenue_ttm, fcf_ttm}'

# the valuation itself
curl -s localhost:6100/valuation/reverse-dcf -H 'content-type: application/json' -d '{
  "revenue": 302.40, "optimized_fcf_margin": 0.35,
  "shares_outstanding": 24.40, "current_price": 224.03,
  "discount_rate": 0.10, "terminal_growth": 0.03, "projection_years": 10,
  "growth_segments": [{"start_year": 1, "end_year": 3, "growth": 0.55}]
}' | jq '.implied_growth'
```

### In VS Code

**Open `suwalski-investing-tools.code-workspace`, not the folder.** Each project has its
own `.venv`, and a single-folder window can only point Pylance at one of them — the other
two then light up with unresolved-import errors. The workspace lists the three projects as
separate roots, each carrying `python.defaultInterpreterPath` to its own environment, so
imports, autocomplete and the Test Explorer work everywhere. `pyright` reports zero errors
in all three projects with that setup.

The workspace also trims the file tree, and the split matters: `files.exclude` hides only
**generated** things (caches, `.venv`, `.artifacts`, `*.pyc`) — nothing in git, nothing you
open. Version-controlled config that you do edit occasionally (`uv.lock`,
`pyrightconfig.json`, the `.code-workspace`, `ruff.toml`, `CLAUDE.md`) is **nested**, not
hidden: collapsed under `README.md` or `pyproject.toml`, one arrow-click away and still
reachable from Ctrl+P. That distinction exists because VS Code has no "show hidden files"
toggle for the explorer — a hidden file is genuinely hard to get back to, so only files you
never need get that treatment. The three
projects appear as their own roots *and* inside "repo root", which is what lets that last
entry carry `docs/`, `scripts/` and `infrastructure/`; drop it from `folders` if the
duplication bothers you more than the convenience is worth.

`.vscode/launch.json` holds debug configurations, each pinned to its project's own
interpreter so breakpoints resolve without any interpreter switching:

| Configuration | What it does |
| --- | --- |
| Run server | `python -m suwalski_investing_server` under the debugger, port 6100 |
| Run server (auto-reload) | the same through `uvicorn --reload` while editing routers |
| rdcf: NVDA example | the CLI with the example arguments, in the integrated terminal |
| rdcf: ask for arguments | prompts for ticker, margin, growth, discount and terminal rate |
| pytest: library / server / cli | that project's suite, `justMyCode` off so you can step into pydantic |

`test-solution` is registered as the default test task (Ctrl+Shift+P → Run Test Task).

Lint and test everything (the gate before any commit):

```bash
./scripts/test-solution.sh
```

Clean up after yourself:

```bash
./scripts/cleanup.sh                 # caches and generated files inside the repo
./scripts/cleanup.sh --all --dry-run # everything, including traces outside it — shows, deletes nothing
```

`--venvs` drops the three environments (`uv sync` rebuilds them), `--system` removes what
lands outside the repo: pytest's `/tmp` directories, yfinance's timezone cache, this repo's
VS Code workspace storage, and — after asking — a prune of the shared uv cache. Nothing
under `/var` is touched, because nothing of ours goes there.

## The inputs

| Input | From a ticker? | Meaning |
| --- | --- | --- |
| `revenue` | yes | TTM revenue — model year 0. The CLI can also derive it from `--fcf / --fcf-margin`. |
| `current_price` | yes | Last traded price — the number the solver has to justify. |
| `shares_outstanding`, `net_debt` | yes | Enterprise value minus net debt, divided by shares, gives the per-share number compared to the price. |
| `optimized_fcf_margin` | **no** | The FCF margin the business is expected to run at. Revenue times this margin is the cash the model discounts. |
| `growth_segments` | **no** | Growth you're asserting, per year range. Everything else is solved. |
| `discount_rate`, `terminal_growth` | **no** | Your required return, and the perpetuity growth after the projection. Terminal must stay below the discount rate. |
| `current_fcf_margin`, `margin_ramp_years` | margin only | Optional: walk linearly from today's margin to the optimized one over N years instead of applying it from year 1. |

The split is the point: a data provider supplies facts, you supply the opinions.

Units are free-form — billions, millions, dollars — as long as revenue, net debt and share
count use the same one. The math and a worked example are in
[`docs/reverse-dcf.md`](docs/reverse-dcf.md).

## Roadmap

- **Web dashboard** — the API is already shaped for it: an "optimized FCF" slider is just
  another value in the request, and every run returns the full year-by-year projection so
  the page can chart it.
- **More providers** — `yfinance` is an unofficial Yahoo scraper. If it starts breaking,
  a keyed provider (FMP, Tiingo) slots in behind the same `TickerSnapshot` contract.
- **Infrastructure** — Kubernetes manifests, Terraform, k9s for day-to-day. Deliberately
  postponed: nothing here is worth deploying yet.
