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
| `suwalski_investing_library/` | The valuation engine, the pydantic contracts, and `marketdata/` (ticker snapshots off Yahoo Finance, year history off SEC EDGAR). The engine half is stdlib + pydantic only — importing it pulls in no scraper. |
| `suwalski_investing_server/` | FastAPI over the engine. Exists so a browser dashboard can call it later. Port 6100. |
| `suwalski_investing_cli/` | `rdcf` — the same engine in the terminal, for fast iteration without a UI. |
| `suwalski_investing_web/` | The UI: React 19 + Vite + Tailwind 4, Catppuccin Mocha. A static build — no Node server to run or deploy. Port 3000. |
| `scripts/` | Entry points: `run/` (server, web), `infra/` (the container stack), plus the CLI, lint+test and cleanup. |
| `compose.yaml` | Both images wired the way the cluster wires them, for local verification. |
| `.artifacts/` | Local scratch: cached ticker snapshots. Gitignored. |
| `docs/` | `reverse-dcf.md` (the model and its math), `guidelines.md` (repo rules). |

Prerequisites: [uv](https://docs.astral.sh/uv/) and [pnpm](https://pnpm.io/). The Python
side is one **uv workspace**: `uv sync` at the root builds a single `.venv` that knows every
package, and `uv.lock` at the root is the only lockfile. The `tickers` extra is what drags in
`yfinance` — the library installed without it is pure valuation math.

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

Browser:

```bash
./scripts/run/server.sh   # API on 6100
./scripts/run/web.sh      # UI on http://localhost:3000, proxying /api to the server
```

The page is a left rail of tools and one open tool — no title bar, no chrome. Assumptions
live in the left panel; growth is either a **single rate** for the whole horizon or a
**split** (near-term years you pin, the rest solved). Every change re-solves, debounced, and
the answer stays in one place: input and solved sit in one card, separated by an arrow with
the solved figure in a filled panel, because it is the finding rather than another input.

The layout fills the viewport rather than scrolling a page: the projection table keeps its
summary pinned to the bottom while its rows scroll, and at 21:9 (>= 2200px) that table moves
beside the chart instead of under it. Type is Inter for text and JetBrains Mono for every
figure — both self-hosted, no CDN — so columns of numbers line up.

HTTP API:

```bash
./scripts/run/server.sh      # Swagger UI at http://localhost:6100/docs

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
`pyrightconfig.json`, `ruff.toml`, `CLAUDE.md`, the web project's configs) is **nested**, not
hidden: collapsed under `README.md` or `pyproject.toml`, one arrow-click away and still
reachable from Ctrl+P. That distinction exists because VS Code has no "show hidden files"
toggle for the explorer — a hidden file is genuinely hard to get back to, so only files you
never need get that treatment. The three
projects appear as their own roots *and* inside "repo root", which is what lets that last
entry carry `docs/` and `scripts/`; drop it from `folders` if the
duplication bothers you more than the convenience is worth.

`.vscode/launch.json` holds debug configurations, each pinned to its project's own
interpreter so breakpoints resolve without any interpreter switching:

| Configuration | What it does |
| --- | --- |
| Run server | `python -m suwalski_investing_server` under the debugger, port 6100 |
| Run server (auto-reload) | the same through `uvicorn --reload` while editing routers |
| rdcf: NVDA example | the CLI with the example arguments, in the integrated terminal |
| rdcf: ask for arguments | prompts for ticker, margin, growth, discount and terminal rate |
| pytest: all projects | the whole suite, `justMyCode` off so you can step into pydantic |
| web (vite dev) | the UI with hot reload |

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

## Run it in containers

The two deployables as the cluster will run them — the server as a wheel on a slim
Python base, the web build as static files behind nginx:

```bash
./scripts/infra/up.sh         # http://localhost:8080
./scripts/infra/list.sh       # what is up, on which ports
./scripts/infra/down.sh       # stop it
```

`up.sh --rebuild` ignores the layer cache and builds both images from zero — for when you
suspect a stale layer rather than a stale source file. `list.sh` says what is up, on which
ports, and where to open it.

Only `web` publishes a port. The browser talks to one origin and nginx proxies `/api` on
to the server, stripping the prefix — the same shape the vite dev proxy has, which is why
the API's CORS list never needs to know about a deployment. Machine-local settings
(`SEC_USER_AGENT` above all) are read from the root `.env`; in the cluster they arrive as
a Secret instead.

Both images build from the **solution root**, because the server resolves the library
through a uv workspace path:

```bash
podman build -f suwalski_investing_server/Dockerfile -t suwalski-server .
podman build -f suwalski_investing_web/Dockerfile -t suwalski-web .
```

Neither runs as root, and neither holds state: the snapshot cache is a 15-minute scratch
directory, so the server stays horizontally scalable with no volume attached.

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

## Where the history comes from

The chart panel has three tabs: the projection, and two views of what the company actually
reported — FCF margin and revenue growth per fiscal year. They exist to make the sliders
arguable: a 35% optimized margin reads differently next to ten years of 20%.

Yahoo carries four or five annual years. **SEC EDGAR's XBRL API** carries as many as the
company filed — ten for KO, ten for MSFT — is free, official, and needs no key, so it is the
primary source with Yahoo as the fallback for symbols EDGAR does not cover (non-US filers).

Two things make that usable rather than merely available:

- **Sources are a list, not a fallback chain.** `DEFAULT_SOURCES` is asked in order —
  EDGAR first for its decade, Yahoo second for the markets EDGAR never sees — and their
  years are merged rather than the first winner taking it. Adding a source is a class with
  `name` and `years()` plus one entry.
- **The cache accumulates years.** EDGAR has no "give me years 4-8" endpoint — `companyfacts`
  is one document with everything — so a request can never be made smaller. What the cache
  does is make it unnecessary: years are stored individually, every fetch is merged into what
  is already on disk, and the network is only touched when the years asked for are not
  covered. Widening the horizon after a fetch has proved the filer has no more years costs
  nothing. Years also survive their source: if EDGAR later drops one, the stored copy stays.
- **Only the continuous tail is charted.** XBRL tags drift, and a company can be missing a
  year in the middle — EDGAR has no capex tag for NVDA between 2013 and 2021. A gap in a
  history chart reads like a collapse, so the unbroken run is what gets returned; the cache
  keeps the orphaned years in case another source fills the hole.

**ADRs are covered too**, because a foreign issuer listed in the US files a 20-F with the
SEC: SE and ASML come back with ten years, TSM with ten (in TWD), GRAB with four — its whole
life since listing. That needs two things the domestic path does not: the `ifrs-full`
taxonomy alongside `us-gaap`, and reading whichever currency the company reports in rather
than assuming USD. Both are handled. EDGAR lists no ticker for some ADRs (Sea Limited files
under CIK 1703399 with `tickers: []`), and guessing by company name is unsafe — EDGAR carries
two "SEA LTD" entries — so those are mapped explicitly through `SEC_CIK_OVERRIDES`.

**Warsaw-listed companies are not in EDGAR at all** — `DNP.WA`, `CDR.WA`, `PKO.WA` all
resolve, but through Yahoo, which means four years instead of ten, in the local currency.
There is no free, licence-clean API with a decade of GPW fundamentals; the data exists on
scraper-hostile sites and in per-company ESEF filings with no central index. One caveat the model cannot know:
the discount rate is yours to set per currency. 10% is a reasonable hurdle in USD; for a
PLN-denominated business, both it and the terminal growth carry higher local inflation.

EDGAR refuses requests without a `User-Agent` that names the tool (and, oddly, refuses ones
that impersonate a browser). Set `SEC_USER_AGENT` to your own "name email" — see `.env.example`.

## Roadmap

- **More providers** — `yfinance` is an unofficial Yahoo scraper. If it starts breaking,
  a keyed provider (FMP, Tiingo) slots in behind the same `TickerSnapshot` contract.
- **Infrastructure** — Kubernetes manifests, Terraform, k9s for day-to-day. Deliberately
  postponed: nothing here is worth deploying yet.
