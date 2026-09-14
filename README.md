# Compiled

A Flask app that serves 27 locally-run machine-learning demos (classification,
detection, segmentation, OCR, face analysis, tracking) and 43 file tools in six
groups — PDF, images, video & audio, privacy, documents & text, data & files —
the kind of utilities that are usually behind a paywall online. A third section,
the **Blockchain** section, has three working chains — a public proof-of-work
ledger, a permissioned proof-of-authority budget ledger for a consortium of
agencies, and a UTXO cryptocurrency with Ed25519-signed spends, mining rewards,
halving and difficulty adjustment — each with an explorer, itemised verification
and a tamper/double-spend demo. A fourth, the **Web Lab**, is a set of live demos of how browsers and servers talk —
the fundamentals (request anatomy, the HTTP methods, status codes, headers and
content negotiation, body encodings), real-time delivery (short polling, long polling, Server-Sent Events, WebSockets,
side by side), HTTP itself (caching and ETags, compression, range requests,
streaming, CORS), server patterns (background jobs, rate limiting,
idempotency keys, signed webhooks with retries, debounce and cancellation) and
auth (cookie sessions vs JWT, a live CSRF attack, OAuth 2 / OIDC against a fake
identity provider, TOTP two-factor), the browser platform (Web Workers,
Service Worker/offline, WebRTC peer-to-peer, WebAssembly, Web Push) and the
data layer (lost updates and locking, N+1 queries, offset vs cursor pagination,
zero-downtime migrations) — 33 demos in a ladder, with the traffic, the SQL and
the numbers visible.

Everything runs on the machine hosting the app. Nothing is sent to a third party.

## Setup

Python 3.12+ and about 14 GB of disk for the model weights. Some tools need
system packages: `ffmpeg` (all video/audio tools), `poppler-utils` (PDF to
images) and `libreoffice` (Word to PDF). A tool whose dependency is missing
says so instead of failing.

```bash
pip install -r requirements.txt
cp .env.example .env            # then set SECRET_KEY
flask --app run db upgrade      # creates app_files/db/app.db
python run.py                   # http://127.0.0.1:5000
```

Model weights are not in the repository. Fetch what you need:

```bash
python scripts/download_models.py --list       # what is present / missing
python scripts/download_models.py --missing    # fetch everything that is not
python scripts/download_models.py classify/vit-base ocr/trocr
```

Models load lazily on first use and stay in memory. The **Free memory** button
in the sidebar (or `POST /models/cache/clear`) unloads them. Loading several
large models at once needs a lot of RAM; run them one at a time on a small box.

## Layout

```
run.py                  entry point -> app.create_app()
app/
  registry.py           the model catalogue (ModelSpec) and shared types
  tools_catalog.py      the tool catalogue: one ToolSpec per tool, grouped by category
  lab_catalog.py        the Web Lab catalogue: one LabSpec per demo, in ladder order
  chain_catalog.py      the three blockchain types
  config.py             environment-driven settings (paths, DATABASE_URL, thresholds)
  core/                 loader (cached weights), uploads, imaging, storage, errors
  db/                   SQLAlchemy models + face matching
  blueprints/
    main.py             home and catalogue pages, cache controls
    models/             one module per task family; routes generated from the registry
    tools/              one module per tool category (pdf, image, video, documents, data)
    chain/              core.py (canonical hashing, Merkle, PoW, Ed25519, SQLite store),
                        ledger.py (public PoW), permissioned.py (PoA, signed budget ledger), coin.py (UTXO coin)
    lab/                realtime.py (poll / long-poll / SSE / WebSocket), http.py (cache, compression,
                        range, streaming, CORS), server.py (jobs, rate limits, idempotency, webhooks, cancellation),
                        auth.py (sessions, hand-rolled HS256 JWT, CSRF, TOTP), oauth.py (client + fake IdP),
                        browser.py (service worker route, WebRTC signalling, Web Push with VAPID),
                        data.py (its own lab.db + SQL recorder: locking, N+1, pagination, migration),
                        basics.py (echo, a REST to-do resource, every status code, negotiation, body decoding)
  static/wasm/mandel.wasm   hand-assembled by scripts/build_wasm.py (no toolchain needed)
  templates/            layout.html, one generic model runner, custom pages where needed
  static/css            tokens.css (design system), base, layout, components
  static/js             theme, ui helpers, the model runner, per-page scripts
migrations/             Alembic (flask db migrate / upgrade)
scripts/                download_models.py, train_sentiment.py
app_files/              data: models/, tools_files/, db/  (gitignored)
```

## Adding a model

1. Put the weights in `app_files/models/<dir>` (or add a source to
   `scripts/download_models.py`).
2. Add one `ModelSpec` to `app/registry.py`. Pick an existing `loader` and
   `view`, or:
3. Write a handler in the matching `app/blueprints/models/<family>.py`,
   decorated with `@predictor('<category>', '<view>')`. Use `read_image()`,
   `loader.get(spec.slug)` and return `ok(...)`.

The sidebar, catalogue, URL, and cache entry come from the registry entry.
The generic `models/run.html` template covers any image/text -> result page;
`spec.render` picks how `runner.js` draws the response (`predictions`,
`detections`, `segments`, `text`, `tags`, `label`, `sentiment`, `similarity`).

## Adding a tool

1. Add a `ToolSpec` to `app/tools_catalog.py`: category, picker (`input`,
   `accept`), extra `fields`, and how the result renders (`render`).
2. Write `@runner('<slug>')` in the matching `app/blueprints/tools/<category>.py`.
   Create a `Job`, write output files into `job.dir`, return `result(job, ...)`.

The page, sidebar entry, catalogue card, `/run`, `/download` and `/preview`
routes all come from the spec. Results are per-browser-session and purged
after `TOOL_JOB_TTL_HOURS`.

## Web Lab

Every real-time demo reads the same in-process ticker (`app/blueprints/lab/realtime.py`),
so comparisons are fair. The client transports live in `app/static/js/lab.js` and
share one interface, which is how the comparison page drives all four at once.
WebSockets use `flask-sock`; the dev server runs threaded (`run.py`), which long
polling, SSE and WebSockets all need. `POST /lab/api/ticker/outage` makes the
feed refuse connections for a few seconds so reconnect behaviour can be watched.

The CORS demo needs no second server: the page calls the same process through
the other hostname (`localhost` vs `127.0.0.1`), which the browser treats as a
different origin. Compression uses the Resource Timing API to read transfer
sizes; the brotli variant needs the `Brotli` package.

The webhook demo makes this server POST to a URL; for safety it only accepts
addresses on this machine. Its default target is its own `/webhooks/inbox`,
which verifies the Stripe-style `t=…,v1=…` HMAC signature and can be switched
to fail or stall so the retry schedule (0, 1, 2, 4 s) can be watched. All lab
state is in-process and resets when the server restarts.

The auth demos use their own cookies (`lab_sid`, `lab_totp`) and never touch
the app's Flask session. The JWT is implemented by hand (HS256) so its parts
can be shown; the fake identity provider at `/lab/idp/*` implements the
authorization-code flow with PKCE, one-shot codes and an OIDC `id_token`. The
TOTP demo works with any real authenticator app — scan the QR it generates.

Browser-platform demos: the service worker is served from `/lab/sw.js` with a
`Service-Worker-Allowed` header and registered with a narrow scope so it cannot
interfere with other pages. WebRTC uses the WebSocket only for signalling; media
is peer-to-peer (open the page in two tabs). Web Push needs internet access to
the browser vendor's push service; VAPID keys are generated once into
`app_files/db/vapid.json`. The WebAssembly module is built by
`python scripts/build_wasm.py`, which assembles the binary by hand.

The data-layer demos use a separate SQLite file, `app_files/db/lab.db`, with
its own SQLAlchemy engine, so they can rewrite rows and schema freely without
touching the app's real tables. It is created and seeded on first use;
`GET /lab/api/data/reset` rebuilds it.

## Blockchain

Three chains share one core (`app/blueprints/chain/core.py`): every hash is
SHA-256 over canonical JSON, transactions are content-addressed, headers commit
to a Merkle root and the previous hash. They differ in consensus: the public
ledger and the coin use proof of work (difficulty 1–5, interactive); the
permissioned ledger uses proof of authority — Ed25519 validator signatures, with
balances derived by replaying the chain. State lives in `app_files/db/chain.db`
and every chain has a reset. Old `/blockchain` and `/blockchain2` URLs from the
previous version redirect here. The permissioned demo accounts are
`treasury/treasury123`, `dof/dof123`, `deped/deped123`, `doh/doh123`,
`auditor/audit123`; keys and password hashes are generated on first run.

## Database

SQLite by default at `app_files/db/app.db`. Three tables:

- `person` — a name
- `face_embedding` — normalised float32 vectors (raw bytes, several per person)
- `recognition_log` — one row per identification attempt

Schema changes go through Alembic:

```bash
flask --app run db migrate -m "describe the change"
flask --app run db upgrade
```

To use MySQL, start the server, create a database, and set `DATABASE_URL` in
`.env` to `mysql+pymysql://user:password@localhost/dbname`. The same migrations
apply.

Face management from the shell: `flask --app run faces list` and
`flask --app run faces forget <id>`.

## Checks

```bash
flask --app run routes-smoke     # renders every page, fails on any non-200
```

## Old URLs

Every URL from the previous version (`/models/objectdetection1`,
`/models/insightface3`, `/tools/tool1`, ...) returns a 301 to its replacement.

## Notes

- `app_files/models/yolov8/` and `stable_diffusion/` are referenced by no code
  and `ultralytics` is not installed; they can be deleted to reclaim space.
- The live face pages stream the **server's** camera as MJPEG, which only makes
  sense when the browser and server are the same machine.
