# AGENTS.md

**suwinvtools** (short for suwalski-investing-tools — the internal name: packages, database,
containers, chart, domain `suwinvtools.k8s.suwalski.internal`): a homelab investing toolkit —
the reverse DCF and the monthly AI cycle signals. Project-specific rules are in section 12.

Rules for anyone — human or AI agent — changing this repository. `CLAUDE.md` only points
here; this file is the one to edit.

## Template upstream: good practices flow back to solid-app-tpl

This repository is, or was created from, **solid-app-tpl** (`~/repos/solid-app-tpl/`) — the
template every new app starts from. Projects created from it keep this section in their own
AGENTS.md; it is what keeps the template alive.

**When a task introduces a good practice of running a repository** — a new gate step, a
convention for layout or naming, a script, a CI job, a rule in this file, a fix to the
tooling — **and `~/repos/solid-app-tpl/` exists on this machine, bring it to the template
too, in the same task:**

- in its generic form: `suwinvtools` names, no feature or domain code, no secrets, no addresses;
- with the template's gate green afterwards (`./scripts/.internal/check.sh` there), and
  `init-project.sh` updated when it rewrites the new files;
- and say in the summary what went to the template. Features and domain rules stay in the
  project; only how the repo is *run* travels.

In the template itself this section applies the other way round: a change here is a change
every future project inherits, so it must stay generic and fully green.

## Git: commits go through suwgit, and only through it

**Agents never run `git commit`, `git push`, amend, reset, rebase or stash** — nor stage
files by hand (`git add`, `git mv`). When a change is finished **and `just check` is green**,
the agent commits and pushes it with one command:

```sh
suwgit push --b2b me --project "<Project>"
```

`<Project>` is the project's name for the owner's work reports — here **`Investing`**:
`suwgit push --b2b me --project "Investing"`. suwgit writes the message with the owner's local model, records the work as B2B
for the owner, and pushes the current branch. Work happens on a feature branch, never on
`master`. A change with a red gate is not committed — it stays in the working tree, and the
summary says why. Anything beyond this (merging, deploying, a force push) is the owner's.

**A repo without git** (a fresh copy of the template, a new project folder) is initialised
with `master` as the main branch — `git init -b master` — never `main`: CI publishes images
only from `master` (`.github/workflows/ci.yml`), and every repo here uses that name.
Initialising is allowed; the first commit is still the owner's.

## 0. KISS & YAGNI — the first rule

The repo grows **only when a real need shows up**. One developer maintains it after hours;
every moving part is a part someone has to keep alive.

- **No dependencies "for later".** A package is added in the same change as the first code
  that imports it. (The template's own dependencies are the exception: they are what the
  gate below runs on.)
- **No configuration for scenarios that do not exist yet.** No settings, env vars, chart
  values, nginx directives or compose services until something reads them.
- **No abstraction before the second use.** Extract when the second caller arrives.
- **No new component without a reason stated in the change.** Database, queue, cache,
  worker, sidecar — each one arrives with the feature that needs it.
- **Prefer deleting to adding.** If a change makes something unused, remove it in the same
  change.
- **When in doubt, leave it out** — and say in the change what was left out and why.

## 1. What lives where

| Path | Holds |
| --- | --- |
| `suwinvtools_library/` | the valuation engine, the pydantic contracts and `marketdata/` (Yahoo, SEC EDGAR). The engine half is stdlib + pydantic only; shared by the server and the CLI (section 12) |
| `suwinvtools_cli/` | `rdcf` — the reverse DCF in a terminal (`just rdcf …`) |
| `suwinvtools_server/` | the HTTP API (FastAPI, PostgreSQL through psycopg, plain SQL), the MCP server at `/mcp` and the signals job (`signals/`, run by `just signals …` and the chart's CronJob). Package in `suwinvtools_server/suwinvtools_server/`, tests mirror it in `suwinvtools_server/tests/` |
| `suwinvtools_server/suwinvtools_server/migrations/` | numbered SQL migrations, applied at start-up, checksummed (`db.py`) |
| `suwinvtools_web/` | the web app (React, Mantine, Vite). Source in `src/`, one folder per feature |
| `deploy/chart/` | the Helm chart the cluster runs: server, web, ingress, the signals CronJob, the cache volume and `templates/smoke-test.yaml`, the post-deploy smoke test |
| `compose.yaml` | the whole stack on a laptop, from the same Dockerfiles — no cluster needed |
| `suwinvtools_server/Dockerfile`, `suwinvtools_web/Dockerfile` | the two images; build context is the repo root |
| `justfile`, `.just/` | commands for humans: the main recipes and the `just <module>` families (section 10) |
| `scripts/.internal/` | everything the gate, CI and `just` run (section 10) |
| `.github/workflows/ci.yml` | CI: the gate, the browser tests, then the images |
| `.artifacts/` | everything generated (e2e reports, renders); outside git and the images |
| `.editorconfig`, `.gitattributes`, `.python-version` | the shared standards: UTF-8 and LF everywhere, binaries never diffed as text, lockfiles and `openapi.d.ts` marked generated, Python 3.14 locally as in the image and CI. A new binary or generated file type gets its line in `.gitattributes` |

## 2. Three ways to run it — all three always work

1. **On the host, while developing:** `just db up`, `just server`, `just web` →
   http://localhost:3240. Fastest loop, hot reload.
2. **The container stack:** `just up` → http://localhost:8094. The same images the cluster
   runs, wired the same way (web proxies `/api` to server), with its own database volume.
   This is how a change is proven to work *without deploying it*.
3. **The cluster:** `deploy/chart/` installed by Argo CD from the platform repo, which sets
   the image tag and creates the secrets.

**The repo always carries all three:** both Dockerfiles, `compose.yaml` and `deploy/chart/`
**with its smoke test** (`templates/smoke-test.yaml`).
They are not optional extras added "when we deploy" — a project without them cannot be run
the way production runs it. Consequences:

- **A new service** (a converter, a cache, a worker) is added to `compose.yaml` **and** to the
  chart in the same change, wired the same way: same names, same env vars, no published port
  unless the browser talks to it.
- **A new env var** gets a working local default in `settings.py`, a commented line in
  `.env.example`, the value for compose in `compose.yaml` and for the cluster in the chart
  (section 7 for secrets).
- **Images build from the repo root** with the root lockfiles; every image pins its base and
  every external image is pinned to a version, never `latest`.
- The gate renders the chart (`helm lint` + `helm template`) and validates `compose.yaml`
  (`podman compose config`); `just up` is the manual proof that the images really start.

## 3. The quality gate

`./scripts/.internal/check.sh` is **the** gate: CI runs exactly this script, `just check` is
the same thing for humans. Run it before calling any change done. It prints a PASS/FAIL/SKIP
report and exits non-zero on any failure.

| Step | Guards |
| --- | --- |
| ruff, ruff format | Python lint (wide rule set, `ruff.toml`) and formatting |
| pyright strict | Python types. No `# type: ignore` / `# noqa` without a comment saying why |
| import-linter | the server's import contracts (section 4) |
| pytest | server tests against a real PostgreSQL (`just db up` locally, a service in CI), incl. `test_contracts.py`: every server module has a layer |
| tsc (app + node) | TypeScript strict plus the extra flags in `tsconfig.app.json`; `tsconfig.node.json` covers the Vite config and the e2e tests |
| eslint | typescript-eslint `strictTypeChecked` + `stylisticTypeChecked`, react-hooks, and the web import contracts (section 4) |
| prettier | web formatting: every file of the web app (TS, TSX, JSON, CSS, HTML, YAML) is checked with `prettier --check` and fails the gate when unformatted. `just fmt` (or format-on-save in VS Code) fixes it; the style lives only in `.prettierrc.json` |
| vitest | web unit tests (`<name>.test.ts`) |
| knip | dead code on the web side: unused files, exports and dependencies. Every repo with a TypeScript frontend runs it; an `ignore` in `knip.json` needs a reason next to it |
| API types | `suwinvtools_web/src/api/openapi.d.ts` matches the server's OpenAPI (`just api-types`) |
| helm | the chart lints and renders, and every annotation and label name fits Kubernetes' 63-character limit after the slash (the API server would refuse it only at deployment) |
| shellcheck | the scripts and the git hooks |
| gitleaks | no secret anywhere in the git history, nor in uncommitted changes. The `.githooks/pre-commit` hook runs it on every commit too (enabled by `just sync`); CI installs a pinned version, so there it never skips |
| compose | `compose.yaml` resolves |

**Browser tests** are separate: `./scripts/.internal/e2e.sh` (`just e2e`) runs Playwright
against a real server and an empty database of its own, on ports apart from the ones you
develop on. A test that fails in CI is retried once, only so the report tells a steady failure
from a flaky one; passing on the retry still fails the job (`failOnFlakyTests`) — flaky is a
bug, in the test or in the app. **CI** runs three jobs: `test` (the gate), `e2e`, and `build`,
which builds the images only when both are green and publishes them only from `master`.

**After deploy**, Argo runs `deploy/chart/templates/smoke-test.yaml` (a PostSync Job with
curl): a handful of read-only requests through the real Services, the way traffic arrives
from the tunnel. A failure turns the sync red and the Job's log says what broke. **Every
chart has this Job** — it is the only check that runs against the real cluster, with its
real secrets, database and routing. It stays small and fast: status codes and a fragment of
the body, no logging in, no writes. Today it checks that nginx answers (`/healthz`) and that
the page reaches the server, which only starts with its database (`/api/health`).

A step that cannot run (a tool missing on a fresh machine) reports **SKIP**, never PASS.
Never weaken a step to make a change pass — fix the change.

### A new feature brings its checks along

Every kind of check the repo has applies to new code too. Before calling a feature done, go
through the list and add what fits — or say in the change why something does not apply:

- **Types** strict on both sides; no `Any`/`unknown` escape hatches without a reason. A closed
  set of values is a type of its own — a `StrEnum` on the server (its values are what the
  database and the API carry), a union of string literals on the web — never a bare `str`
  with the allowed values in a comment.
- **Formatting:** ruff format on the server, Prettier on the web — run `just fmt` before the gate; never hand-format against them or add files to `.prettierignore` to dodge them.
- **Unit tests** for every module with rules: `suwinvtools_server/tests/` mirrors the package on
  the server, `<name>.test.ts` sits beside the file on the web.
- **A browser test** (`<name>.e2e.ts` beside the code) when users click it: the path a user
  relies on, not every button.
- **Import contracts:** the new module or folder gets its place (section 4), in the same change.
- **Dead code:** knip stays clean; remove what the change made unused.
- **Database:** schema changes go into a new numbered migration, never an edited one; the
  queries get tests against the real PostgreSQL.
- **API:** after changing a model the API exposes, regenerate `openapi.d.ts` (`just api-types`).
- **An outside service** (an API, a public dataset, a geocoder — anything not ours): the gate
  tests the code against a recorded answer, but the service can change its answer without a commit
  here. So the first feature that calls one brings, in the same change:
  - **a live test** — the real call, marked `@pytest.mark.live` and left out of the gate
    (`addopts = ["-m", "not live"]`), run by `scripts/.internal/live-check.sh`;
  - **a daily check from production's network** — a CronJob in the chart, the server's image with
    another command, asking the real services through the production code and database inside a
    transaction it rolls back; when something is wrong it posts to the project's Discord alerts
    channel (a webhook in a Secret the platform repo's `setup.sh` creates). Not a GitHub workflow:
    a service can block GitHub's runners while answering production, and then the alarm is about
    GitHub. Keep it light — once a day, a small area, no retries — within each service's terms;
  - **a failure that degrades, not breaks:** reading the answer counts as part of the call — a
    missing field or a new shape is handled like the service being down (keep the last good data,
    say it may be old), and nothing stored is replaced until the new answer has been read whole.

  `grzyby-mcp` is the reference — read it in `~/repos/grzyby-mcp/`, or at
  https://github.com/Manomenu/grzyby-mcp when it is not on this machine:
  `grzyby_server/grzyby_server/miejsca/live.py` (the check), `deploy/chart/templates/live-check.yaml`,
  `grzyby_server/tests/live/`, `grzyby_server/grzyby_server/lasy/zakazy.py`. Its daily check caught
  a public dataset dropping a field the day it happened — and, run from GitHub, was then blocked
  there, which is why it moved to the cluster.
- **Deployment:** compose and the chart learn about the new service or setting (section 2).
- **Smoke test** (`deploy/chart/templates/smoke-test.yaml`): add a line when the feature
  brings something that can break only on the cluster and can be checked without logging
  in — a new service or dependency, a new secret or config read at start-up, a new public
  route, a change to nginx routing. Anything behind a login belongs in the e2e tests.

## 4. Import contracts: which part may import which

Both sides are layered: a part may import the parts **below** it, never above it or beside
it. "Below" means more basic — knows less about the rest. The order is checked by the gate,
not by reviewers; an import against it fails with the import chain.

| | Server | Web |
| --- | --- | --- |
| Where | `[tool.importlinter]` in `pyproject.toml` | `boundaries/*` in `suwinvtools_web/eslint.config.js` |
| Today | `app` → `db` → `settings` | `main`/`App` → features → `api` |
| A new feature | **must** get a layer in the first contract — `tests/test_contracts.py` fails otherwise | is a folder `src/<feature>/`, independent of other features by default |
| Inside a feature | a package declares its own order (e.g. `api` → `store` → `model`) as a contract with `containers` | free |
| Feature uses feature | only downwards, by its position in the layer list | only through an explicit policy in `eslint.config.js`, with a comment saying why |

`pyproject.toml` and `eslint.config.js` each carry a commented example of adding a feature.

- **Respect the order.** If code seems to need an import against it, the code is in the
  wrong place: move it down to a shared level, or pass it in from above — do not loosen a
  contract to make an import pass.
- **A contract change is a design change.** Say in the change why the new edge exists.

## 5. Layout: by feature, the same on both sides

**The app grows by features.** This is the preferred — default — way to extend it: the
code that makes one feature work is kept together in **one folder**, on each side, named
after the feature (`notes/`, `export/`, `billing/`), not spread across folders by technical
kind (`models/`, `services/`, `components/`, `hooks/`). A folder holds everything that
changes together: on the server its routes, models, SQL and tests mirror; on the web its
screen, components, hooks, logic, HTTP calls and their tests beside them.

Why: a change to one feature then touches one folder per side, a feature can be read,
reviewed, moved or deleted as a whole, and the import contracts (section 4) can keep
features apart. A layer-first layout does the opposite — every change cuts across all of it.

In practice:

- **A new capability starts as a new folder**, or goes into the existing feature it
  belongs to — never into a shared bucket. Name it in the users' terms, the same on both
  sides, so `suwinvtools_server/suwinvtools_server/notes/` and
  `suwinvtools_web/src/notes/` are obviously one thing.
- **Shared code is the exception and is earned:** it moves down to a shared level only when
  a second feature really needs it, and only as plumbing (`db.py`, `api/client.ts`) — never as
  a grab-bag of helpers.
- **Projects created from this template keep this rule** in their AGENTS.md: it is how they
  are meant to grow, not a suggestion for the first week.

A change to one feature should touch one place on each side.

- **Server:** a feature with more than one concern is a package (`notes/`: `model.py` for
  what the API sends and receives, `store.py` for the SQL, `api.py` for the routes); a single
  concern stays one module (`db.py`). Its router is included in `app.py`.
- **Server data classes — pydantic at the boundary, dataclass inside.** A pydantic `BaseModel`
  is for data that crosses the process boundary: what the API or an MCP tool sends and receives
  (it becomes their schema) and settings. Its fields are a contract with someone outside —
  renaming one breaks a client — and input from outside deserves validation. A frozen
  `@dataclass` is for values that live only inside the server: a row from our own SQL, an
  intermediate result. They change freely, and their types are already checked by pyright;
  pydantic there would only validate twice and quietly coerce a bug (`"67"` into `67`) instead
  of failing. So the kind of class tells a reader whether changing it changes the API.
- **Web:** one folder per feature under `src/`, holding its components, hooks, logic and its
  HTTP calls (`<feature>/api.ts`, typed from `api/openapi.d.ts` — no hand-written copies of
  server models). `api/` is the only shared folder: HTTP plumbing.
- **No catch-all folders** (`ui/`, `components/`, `utils/`, `helpers/`, `common/`). A piece
  that seems to belong nowhere usually belongs with others that change together: name that
  feature and give it a folder. The same question applies on the server.
- **Logic out of components.** Anything with rules is a plain `.ts` module with a
  `.test.ts` beside it; components and hooks only wire it to React.
- **Files:** a component per `PascalCase.tsx`, hooks `useSomething.ts`, other modules
  `camelCase.ts`. Shared e2e steps, once there are some, live in `suwinvtools_web/e2e/helpers.ts`.
- **State:** component state and props. No global store and no data-fetching library until
  a second screen needs shared server state.

### 5.1 The web app (React) — practices

The frontend is React 19 with Mantine and Vite, TypeScript strict. `src/health/` is the
template's one feature and shows the pattern end to end: `api.ts` → `status.ts` (+ test) →
`ServerStatus.tsx` (+ e2e test).

- **One feature, one folder**, holding its screen, hooks, logic and `api.ts`. `App.tsx` only
  puts features together; `main.tsx` only sets up providers and the theme.
- **Types come from the server.** A feature's `api.ts` calls `request<T>()` from
  `api/client.ts` with `T` taken from `api/openapi.d.ts`. No hand-written copies of server
  models, no `fetch` outside `api/client.ts`, no host names: the browser always calls `/api`
  on its own origin (the Vite proxy in development, nginx in the image).
- **Logic out of components.** Rules (parsing, formatting, state machines, saving) are plain
  `.ts` modules with a `.test.ts` beside them; components and hooks only connect them to
  React. If a component needs a test of its own to cover a rule, the rule is in the wrong
  file.
- **Effects are safe to run twice.** `StrictMode` runs every effect twice in development:
  every request in an effect gets an `AbortController` and ignores its result once aborted;
  one-off actions (a notification, a migration of stored data) happen where code runs once,
  not in a component that may mount twice.
- **Never block the user on the network.** Typing and clicking change local state at once;
  saving happens in the background — debounced, one request in flight, retried when it
  fails — and a small status shows where it stands (saving / saved / offline), instead of a
  spinner over the form. A conflict (409) is shown to the user, never silently overwritten.
- **Errors reach the user in their language.** `api/client.ts` turns every failed response
  into an `Error` with the server's `detail`; a validation error (422) maps onto the fields
  it belongs to. No raw stack traces, no silent `catch`.
- **Mantine first.** Layout and spacing through Mantine components and props, colours from
  the theme (`main.tsx`). A global stylesheet (`src/app.css`) only when Mantine has no prop
  for it, with classes named after the feature (`.draft-row`), not inline style objects that
  are repeated.
- **Accessible names are the test contract.** Interactive things are real buttons, links and
  inputs with a visible label or an `aria-label` (an icon button: `aria-label="Konto"`).
  That is what screen readers read and what the e2e tests find them by.
- **Numbers that shape the layout are named constants** (`NAVBAR_WIDTH`), exported, and tests
  compute expectations from them — a test that hard-codes 220 breaks on a design tweak.
- **The browser's storage is for conveniences only** (a panel width, the last tab): read it
  defensively (it can be empty, full or blocked) and validate what comes back. Anything the
  user would miss lives on the server.
- **Browser tests** (`<name>.e2e.ts` beside the code) find elements by role and visible text,
  use `exact: true` (a substring match passes on the wrong text), create their own data and
  never depend on another test's. They test what a user relies on, not every button.
- **Dependencies:** Mantine's packages come in only when used (`@mantine/dates` with the
  first date field, `@mantine/notifications` with the first notification), each in the same
  change as its provider and stylesheet in `main.tsx`.

## 6. File nesting: a file and its companions are one entry

Tests and companions sit **beside** the file they belong to and share its name, so the
editor folds them under it (`.vscode/settings.json`, `explorer.fileNesting.patterns`):

```
drafts.ts               ▸ drafts.ts
drafts.test.ts            ├ drafts.test.ts
drafts.e2e.ts             └ drafts.e2e.ts
Panel.tsx               ▸ Panel.tsx
Panel.test.ts             ├ Panel.test.ts
Panel.e2e.ts              └ Panel.e2e.ts
```

- Name companions `<name>.<role>.ts` — `.test.ts` (vitest), `.e2e.ts` (Playwright),
  `.stories.tsx` etc. — never `test_<name>.ts` or a separate `__tests__/` folder; a
  differently named file falls out of the nesting.
- Configuration nests under its owner: `pyproject.toml` ▸ `uv.lock`, `pyrightconfig.json`;
  `package.json` ▸ lockfile, eslint, prettier, knip, tsconfig, vite; `.env.base` ▸ `.env`,
  `.env.example`; `README.md` ▸ the repo-level files.
- A new kind of companion or config file gets a pattern in `.vscode/settings.json` in the
  same change, rather than cluttering the explorer.
- Python tests cannot sit beside the module (pytest and the wheel would mix them), so the
  server mirrors the package in `tests/` instead — same names, `test_<module>.py`.

## 7. Secrets

**No secret value ever enters this repo** — not in code, not in `.env.example`, not in
`values.yaml`, not in a test. `.gitignore` keeps `.env`, `.secrets/` and key files out;
gitleaks checks every commit (the pre-commit hook) and the whole history (the gate). A hit is
never silenced with an allowlist entry for a real value — remove the value and rotate it.

- **On a laptop:** development values (a test API key, a local password) go in `.env` — at
  the root or in a project directory — which is gitignored. `.env.example` documents each
  variable with a placeholder. **`just secrets backup`** copies those `.env` files into
  Bitwarden (folder Homelab, one Secure Note per file, `suwinvtools/<path>`), **`just secrets
  restore`** brings them back on a new machine (`--force` to overwrite a file that differs).
  The logic is `scripts/.internal/secrets.sh`; the `bw` CLI must be logged in once
  (`bw config server https://vault.bitwarden.eu && bw login`). After adding or changing a
  value in a `.env`, tell the owner to run `just secrets backup`.
- **On the cluster:** secrets are owned by the platform repo (`suwalski-platform`), never
  by this one. Each lives in that repo's `.secrets/<project>[-<env>].env`, is entered once
  by `scripts/projects/<project>/[<env>/]setup.sh`, which creates the Kubernetes Secret, and
  is backed up to Bitwarden with **`just secrets backup`**; a new machine gets them back with
  **`just secrets restore`**. The chart only names the Secret (`server.databaseSecret` and
  the like) and reads it through `envFrom`.
- **A new secret, step by step:** a setting in `settings.py` with a working local default
  (or none, if it has no safe default); a placeholder line in `.env.example`; the Secret's
  name as a chart value; the prompt in the platform repo's `setup.sh` (its AGENTS.md, „Nowa
  zmienna”). **End the change by telling the owner** to run that `setup.sh` and then
  `just secrets backup` there. Agents never log in to Bitwarden or run the backup themselves.
- Not a secret — a URL, a port, a public name — goes in plain sight: `values.yaml`, a
  ConfigMap, `.env.base`.

## 8. Network access and login: through Cloudflare

The app does **not** build its own login, sessions or passwords, and its ports are never
opened to the internet. Reaching it and logging in both go through Cloudflare, configured in
the platform repo:

- **Network access:** a Cloudflare Tunnel from the cluster — no port forwarding, no public IP.
  The chart's ingress host is what the tunnel points at.
- **Who may log in:** Cloudflare Access in front of the address — a one-time code by email
  (or a Google/GitHub login) for an allow-list of addresses kept in the platform repo
  (`terraform/edge/access/<group>.json`, filled by the project's `setup.sh`). Adding a
  user is a change there, not here.
- **Who is logged in, inside the app:** every request carries Access's signed token in the
  `Cf-Access-Jwt-Assertion` header. The server **verifies** it (signature from the team's
  public keys, the application's audience tag) and takes the email from it — never trusts a
  plain email header. The team domain and audience come in as config (a ConfigMap from the
  platform repo), not secrets. `automat-operat`'s `identity.py` is the reference
  implementation: a `current_user` FastAPI dependency, `/me` for the web app, and logout as
  a link to `/cdn-cgi/access/logout`.
- **On a laptop** there is no Cloudflare: a `DEV_USER_EMAIL` setting stands in for the token,
  only when set, and never on the cluster.
- **Public parts** (a landing page, a public API or MCP endpoint) get an Access *bypass*
  policy for their path in the platform repo, and their own protection where it matters:
  rate limiting in Cloudflare, read-only endpoints, no personal data.
- Until the app has users, none of this is wired: the template has no identity module. It
  arrives with the first feature that needs to know who is asking (section 0).
- **This project today:** home network only — `*.k8s.suwalski.internal` does not go through the
  tunnel, there is no Cloudflare layer and no login (like `suwageval`).

## 9. Naming

Two vocabularies, chosen word by word:

- **Domain words in the users' language.** What the users' work is made of — its things, their
  attributes, the terms of the trade — is named the way the users say it. When they speak
  Polish about their domain, those names are Polish (without diacritics) and map 1:1 onto their
  documents and data sources: `faktura`, `kontrahent`, `pozycja`, `stawka_vat`.
- **Software words in technical English.** Everything that exists only because there is
  software: modules and files named by their role (`store.py`, `sources.py`, `search.py`,
  `api.py`, `importer.py`), verbs (`fetch`, `replace`, `refresh`, `search`, `export`), generic
  fields (`id`, `name`, `kind`, `created_at`), infrastructure (caches, jobs, settings, env
  vars, chart values), API routes, test helpers, CSS classes.
- **One name often holds both:** English structure around domain nouns — `fetch_faktury()`,
  `replace_kontrahenci()`, `faktury_overdue()`, `class Faktura`, the table `faktury` next to
  `fetch_log`. A feature folder is named after its part of the domain (`faktury/`,
  `kontrahenci/`); the modules inside it after their technical role.
- **The test:** would a user say the word about their work? Domain language. Would only a
  programmer? English.
- **Text people read** is in the users' language regardless: labels and messages, and
  everything a chatbot reads — an MCP tool's name, parameters, description and answer fields.

## 10. Commands: `justfile` vs `scripts/.internal/`

- **`justfile` is for humans.** `just` lists every recipe, grouped: `run` (dev servers),
  `dev` (code generation), `infra` (the container stack), `maintenance` (check, e2e, fmt,
  sync), plus modules in `.just/`: `db` (`.just/db.just`: the local PostgreSQL) and
  `secrets` (`.just/secrets.just`: the `.env` files in Bitwarden). New human-facing commands
  go there, into the matching group; a family of related commands becomes a module of its
  own — a file in `.just/`, mounted with `mod <name> '.just/<name>.just'` and starting with
  `set working-directory := ".."`, so its recipes run from the repo root like the rest.
- **`scripts/.internal/` is for machines** — CI, `just` recipes and agents. Logic longer than
  a line or two lives here as a `.sh`, and the recipe only calls it.
- **Agents call these directly:**

  | Script | Use it to |
  | --- | --- |
  | `scripts/.internal/check.sh` | verify a change — the whole gate (section 3) |
  | `scripts/.internal/e2e.sh [playwright args]` | browser tests (`suwinvtools_web/src/**/*.e2e.ts`) against a real server and an empty `suwinvtools_e2e` database, on ports 6241/3241. Run it after changing anything a user clicks |
  | `scripts/.internal/db.sh up\|down\|status\|psql` | the local PostgreSQL on `localhost:5473` (podman container `suwinvtools-postgres`). `check.sh` runs `up` itself; tests create their own `suwinvtools_test` database |
  | `scripts/.internal/api-types.sh [--check]` | regenerate `suwinvtools_web/src/api/openapi.d.ts` after changing a model the API exposes. Never edit that file by hand |
  | `scripts/.internal/secrets.sh backup\|restore` | **not for agents** — the owner's copy of the `.env` files in Bitwarden (`just secrets`, section 7); it asks for the master password |
  | `scripts/.internal/infra-status.sh` | what of the compose stack is up and on which ports (needs `jq`) |

  A new helper an agent should reach for goes here too, with a row in this table.

## 11. Behavioral guidelines

Guidelines to reduce common LLM coding mistakes.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 11.1 Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 11.2 Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 11.3 Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan with a check per step. Simplicity rules are in
section 0.

### 11.4 Delegate well-defined work to a cheaper model

**Larger, well-defined tasks go to a subagent on Sonnet** — to save tokens. Well defined
means: a clear goal, the files it touches are known, and a check says when it is done
("port X to Y with `check.sh` green", "write the tests for Z", "rename A to B everywhere").

- The prompt carries everything the subagent needs: the goal, the files, the rules of this
  file that apply, and the acceptance check. It starts with no context of its own.
- The main agent keeps what needs judgment: design decisions, unclear requirements, small
  edits (spawning costs more than doing them), and the review of the subagent's result
  against the acceptance check — without redoing the delegated work.

## 12. Project rules — suwinvtools

### 12.1 Architecture invariants

- **The library owns the math and the contracts.** `suwinvtools_library` depends on pydantic
  and the stdlib; every valuation rule lives there, so the CLI, the API and MCP never disagree
  about a number. Server and CLI are adapters: they parse, call one library function, format.
- **Network and disk live in `suwinvtools_library/marketdata/`** (and, for the signals, in
  `suwinvtools_server/signals/sources/`), nowhere else. `valuation/` and `contracts/` never
  import from marketdata — `tests/test_packaging.py` imports the engine in a subprocess and
  fails if pandas, numpy or yfinance came along; the import contracts say the same.
- **Reverse DCF only.** A forward DCF (a target price from guessed years) was built once and
  cut on purpose: the interesting output is the growth the market price demands. Do not bring
  back a forward valuation command, endpoint or tool.
- **A provider supplies facts, never assumptions.** Price, shares, TTM revenue and FCF, net
  debt are observable; optimized margin, growth, discount rate and terminal growth are the
  user's and are never defaulted from fetched data.
- **History sources are a list, asked in order, and their years are merged** (EDGAR has a
  decade for SEC filers, Yahoo four years for every market). **One XBRL tag supplies a
  series**, never a per-year mix of aliases.
- **The web app owns no valuation logic.** Every number it shows comes from a response field.
- **The published-screen regression test** in `suwinvtools_library/tests/test_reverse.py`
  anchors the model to a real result — a change in that number is a bug until proven otherwise.

### 12.2 The signals (`suwinvtools_server/signals/`)

The plan, signal by signal: `docs/notifier.md` links it.

- **A check is `read` + `evaluate`.** `read` fetches and decides readiness (NOT_READY when
  nothing is new, INVALID with a reason when a source changed or data is missing — never a
  guess). `evaluate` is a pure function of the stored history; thresholds are module constants
  that the check's `rule_red`/`rule_green` text is built from, so the page and the code agree.
- **The language model reads, it never knows.** It only gets documents the job fetched, and
  every claim carries a quote that `llm.verify` finds in that document (plus `states_number`
  for the value). A red or green from the news needs two independent outlets or a primary
  source (a filing); otherwise it is UNCONFIRMED and goes to the status channel.
- **Texts people read are Polish** (check titles, rules, summaries, Discord messages, the web).
- **A new check:** a class in the matching `checks/<category>.py`, an entry in
  `checks/ALL_CHECKS`, tests on recorded answers in `tests/signals/`, and — when it calls a
  new outside service — a `@pytest.mark.live` test (`just signals live-check`).
- **litellm is pinned exactly** and bumped in a change of its own, to a release at least two
  weeks old: 1.82.7 and 1.82.8 on PyPI were malicious (March 2026).

### 12.3 Adding a tool

1. Contracts and the pure engine in `suwinvtools_library/` (when it computes), with tests.
2. A feature package in `suwinvtools_server/` (`api.py`, …) with its layer in `pyproject.toml`,
   and — if an assistant should reach it — a tool in `mcp/server.py`.
3. A feature folder in `suwinvtools_web/src/`, and its icon in the tool rail (`App.tsx`):
   an icon with the tool's name in the tooltip; the rail stays icons only.
4. CLI surface only if the tool is genuinely faster from a terminal.

### 12.4 Charts

Chart colour is validated, not eyeballed: series colours are checked against the dark surface
for colour-vision separation and contrast, and identity is never carried by colour alone — the
legend, the hover panel and the table repeat it.
