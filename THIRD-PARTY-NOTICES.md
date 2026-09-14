# Third-party notices

This project is MIT ([LICENSE](LICENSE)). Its dependencies are not all MIT, and two of them
carry obligations that travel with what gets shipped. Nothing here is copyleft that reaches
this project's own source: there is no GPL, LGPL or AGPL anywhere in the tree.

## Fonts, shipped in the web build — SIL OFL 1.1

Inter and JetBrains Mono are self-hosted rather than loaded from a CDN, so the `.woff2`
files are emitted into `dist/assets/` and served from the `web` image. The OFL requires its
notice to travel with those files, which is what these are:

| Font | Notice | Upstream |
| --- | --- | --- |
| Inter | [`suwalski_investing_web/public/fonts/inter-OFL.txt`](suwalski_investing_web/public/fonts/inter-OFL.txt) | [rsms/inter](https://github.com/rsms/inter) |
| JetBrains Mono | [`suwalski_investing_web/public/fonts/jetbrains-mono-OFL.txt`](suwalski_investing_web/public/fonts/jetbrains-mono-OFL.txt) | [JetBrains/JetBrainsMono](https://github.com/JetBrains/JetBrainsMono) |

They live under `public/`, so vite copies them to the root of every build and they are
reachable at `/fonts/inter-OFL.txt` and `/fonts/jetbrains-mono-OFL.txt` on a running
deployment. Neither font declares a Reserved Font Name, so either may be modified and kept
under its own name.

## Everything else

| Licence | Where | What it asks for |
| --- | --- | --- |
| MIT, ISC, BSD-2/3, PSF-2.0 | most of the tree — pydantic, fastapi, uvicorn, starlette, numpy, pandas, react, vite | their own notice preserved in their own files |
| Apache-2.0 | yfinance, requests, typescript | the same; NOTICE preservation would only apply if their sources were vendored here, and none are |
| MPL-2.0 | `certifi` (ships inside the server image), `lightningcss` (build-time only) | file-level copyleft — it triggers only on modifying *their* files, which this project does not do. Both keep their own licence files where the installer put them. |
| CC-BY-4.0 | `caniuse-lite` | a browserslist database used at build time and never shipped |

Container base images (`python:3.14-slim`, `nginxinc/nginx-unprivileged:1.29-alpine`) carry
their own distributions' software under its own licences, GPL'd userland included. That is
ordinary for a redistributed image and does not reach this project's source, which sits
beside those programs rather than linking against them.

## The data is a separate question

The MIT licence covers **this code**. It grants nothing over the data the code fetches,
because that is not this project's to grant:

- **SEC EDGAR** — filings are US government work in the public domain. The only condition is
  EDGAR's fair-access policy: identify the caller (`SEC_USER_AGENT`) and stay under its rate
  limit.
- **Yahoo Finance**, reached through `yfinance` — `yfinance` is Apache-2.0 as *code*, but the
  data behind it is Yahoo's and their terms of service restrict it to personal,
  non-commercial use and forbid redistribution. Anyone running this commercially, or
  republishing what it fetches, needs a provider whose terms permit that.

No fetched data is committed here: `.artifacts/` is gitignored, and the caches are scratch.
