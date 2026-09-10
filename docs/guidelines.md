# Repository Guidelines

Rules for keeping suwalski-investing-tools healthy as it grows. Behavioral guidelines for
AI-assisted coding live in `CLAUDE.md`; this document is about the repository itself.

## 1. Architecture invariants

- **The library owns the math and the contracts.** `suwalski_investing_library` depends on
  pydantic and the stdlib — nothing else. No FastAPI, no HTTP client, no file I/O, no
  network. Every valuation rule lives here, which is why the tests can cover it in
  milliseconds and why the CLI and the server can never disagree about a number.
- **Network and disk live in `suwalski_investing_library/marketdata/`, and nowhere else.**
  It is the only package that talks to a provider or writes a cache file, and its
  dependencies sit behind the `tickers` extra rather than in the library's base
  requirements. `valuation/` and `contracts/` must never import from it — `tests/
  test_packaging.py` enforces that by importing the engine in a subprocess and failing if
  pandas, numpy or yfinance came along. A second provider is a new module behind the same
  `TickerSnapshot` contract, not a change to the callers.
- **History sources are a list, asked in order, and their years are merged.** Not a chain of
  responsibility: that pattern stops at the first handler that answers, and the first answer
  here is often partial — EDGAR has a decade for SEC filers, Yahoo has four years but reaches
  every other market. What the loop borrows is the early exit; once the horizon is covered
  the remaining sources are never called. A new source is a class with `name` and `years()`
  plus an entry in `DEFAULT_SOURCES` — no caller changes. Either being down degrades the
  chart, never the valuation.
- **One tag supplies a series, never a mix of aliases.** XBRL lets a company tag the same
  line item differently across years, and mixing aliases per year silently compares
  incomparable definitions — GRAB has a year tagged at $0.05B next to $1.43B for the same
  period. The alias with the widest coverage wins; the others only fill years it lacks.
- **A provider supplies facts, never assumptions.** Price, share count, TTM revenue, TTM
  FCF and net debt are observable. Optimized margin, growth, discount rate and terminal
  growth are the user's and must never be defaulted from fetched data — that would quietly
  turn the tool's one interesting output into an echo of the provider.
- **The web app owns no valuation logic either.** It renders what the API returns and sends
  back what the user typed; every number it displays comes from a response field. If the
  page starts computing a figure, that figure belongs in the engine, where it can be tested.
- **Server and CLI are adapters.** They parse input, call one library function, format the
  result. Business rules never leak into a router or an argparse handler. If you find
  yourself computing something in `suwalski_investing_server`, it belongs in the library.
- **Contracts are defined once**, in `suwalski_investing_library/contracts/`. The API
  request/response models and the CLI's internal types are the same pydantic models — the
  OpenAPI schema a future dashboard consumes is generated from them, so a field rename is a
  single edit.
- **The engine stays pure and deterministic.** `project()` and `value_per_share()` are
  called tens of times per solve; keep them side-effect free, no logging, no caching, no
  randomness. The solver's contract with the tests depends on repeatability.
- **Validation belongs in the contracts, not in the engine.** Impossible combinations
  (terminal growth above the discount rate, overlapping segments, a fully covered horizon)
  are rejected by pydantic validators, so the engine never has to defend against them.
  Cases the model genuinely cannot answer raise `ValuationError` — the server maps that to
  422, the CLI to exit code 1.

## 2. Configuration

- **Env layering:** `.env.base` (committed defaults) → `.env` (gitignored secrets and
  machine overrides), solution root first, then per-project. Every service uses that order.
  `.env.example` documents what a developer has to fill in.
- Comments in env files go on their **own line** — inline `KEY=value  # comment` parses
  differently across tools.
- New setting checklist: an explicitly typed field in `settings.py` (no `os.environ` or
  `getattr` hacks), a line in `.env.example` with a one-line comment, `extra="ignore"` stays.
- Secrets never enter git. `.env*` is gitignored; when a build context appears, cover it
  with a `.dockerignore` too.

## 3. Quality gates

- **`./scripts/test-solution.sh` must be green before committing**: `ruff check`,
  `ruff format --check`, pytest in every Python project, and `tsc --noEmit` for the web app. Non-zero exit on any failure,
  so it drops into CI unchanged.
- **Formatting is `ruff format`, not taste.** Editors are configured to run it and ruff's
  fixes on save; the gate only verifies. Where a hand-made layout genuinely reads better —
  flag/value pairs in a CLI test fixture, say — fence it with `# fmt: off` / `# fmt: on`
  standing alone on their own lines, and never reformat code your change did not touch.
- Lint config is the root `ruff.toml` — one config for all projects, no per-project
  overrides.
- **Never let a test hit the network.** `build_snapshot` takes plain frames and
  `get_snapshot` takes an injectable `fetch`, precisely so the suite stays offline and
  fast. A test that needs Yahoo to be up is a test that fails on a train.
- **Test the math, not the plumbing.** Valuation logic, parsers and validators get unit
  tests. The published-screen regression test in `tests/test_reverse.py` anchors the model
  to a real-world result — treat a change in that number as a bug until proven otherwise.
- A behavior change and its test update ship in the same commit.

## 4. Charts

Chart colour is validated, not eyeballed. The two series in the projection chart
(your input / solved) were checked against the Catppuccin Mocha surface for
colour-vision separation and contrast before shipping; a new chart with new colours gets
the same treatment. Identity is never carried by colour alone — the legend, the hover panel
and the table all repeat it.

## 5. Adding a tool

The reverse DCF is the first of several. A second one (comparables, owner earnings,
whatever) follows the same shape:

1. Contracts in `suwalski_investing_library/contracts/<tool>.py`.
2. Pure engine in `suwalski_investing_library/<tool>/`, with its own unit tests.
3. A router in `suwalski_investing_server/<tool>/router.py`, registered in `app.py`.
4. CLI surface only if the tool is genuinely faster to drive from a terminal — an unused
   command is a maintenance cost.
5. A UI entry is one object in `suwalski_investing_web/src/tools.ts` plus its component;
   the shell needs no changes.
6. `PYTHON_PROJECTS` in `scripts/test-solution.sh` updated if a new project appeared.

## 6. Leaving no mess

Anything the repo writes outside its own directory has to be removable by
`scripts/cleanup.sh`. When you add a tool that caches, logs or writes state somewhere else,
add the path to that script's `--system` section in the same commit — a trace nobody can
find is a trace nobody cleans. Repo-local scratch belongs in `.artifacts/`, which is
gitignored and swept by the default run.

## 7. Git hygiene

- Branch per change, merged into `master`.
- Lockfiles (`uv.lock`) are committed; `.venv/`, caches and generated output are not.
- Scripts: `set -euo pipefail`, spaces not tabs, `podman` (not `docker`) once containers
  appear, `bash -n` anything you touch.
- Infrastructure comes later on purpose (see `infrastructure/README.md`); don't add
  Dockerfiles or manifests until something actually needs to be deployed.
