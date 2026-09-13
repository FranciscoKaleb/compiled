"""The Web Lab: interactive demos of how browsers and servers talk.

Each demo is a page with three parts — the client, a log of what is actually
on the wire, and a stats bar — so the trade-offs are seen, not explained.
"""
from dataclasses import dataclass

LAB_GROUPS = [
    ('basics', 'Fundamentals', 'What a request is, what a response is, and the vocabulary in between'),
    ('realtime', 'Real-time', 'Getting new data from the server to the browser'),
    ('http', 'HTTP', 'What the protocol itself can do for you'),
    ('server', 'Server patterns', 'The habits that keep a backend honest under load'),
    ('auth', 'Auth & sessions', 'Who is asking, and how the server knows'),
    ('browser', 'Browser platform', 'What the browser can do without a server in the way'),
    ('data', 'Data layer', 'What goes wrong between the app and the database, and the fixes'),
]


@dataclass(frozen=True)
class LabSpec:
    slug: str
    group: str
    title: str
    subtitle: str
    blurb: str
    template: str
    level: int = 1           # position in the ladder, for ordering

    @property
    def url(self) -> str:
        return f'/lab/{self.slug}'

    @property
    def endpoint(self) -> str:
        return 'lab.' + self.slug.replace('-', '_')


LABS: list[LabSpec] = [
    # --- Fundamentals -----------------------------------------------------------
    LabSpec(
        slug='anatomy', group='basics', level=1,
        title='Anatomy of a request', subtitle='What actually goes over the wire',
        blurb='Build a request piece by piece — method, URL, query string, headers, body — send it, and see the exact '
              'bytes the server received echoed back, next to the response it sent.',
        template='lab/basics_anatomy.html',
    ),
    LabSpec(
        slug='methods', group='basics', level=2,
        title='GET, POST, PUT, PATCH, DELETE', subtitle='The verbs and what they promise',
        blurb='A tiny to-do API. Create with POST (201 + Location), replace with PUT, edit with PATCH, remove with DELETE '
              '(204), peek with HEAD, ask with OPTIONS — and see what 405 looks like when you pick the wrong one.',
        template='lab/basics_methods.html',
    ),
    LabSpec(
        slug='status-codes', group='basics', level=3,
        title='Status codes', subtitle='1xx to 5xx, with the companion headers',
        blurb='Pick any status code and get a real response with it: 301 that fetch() follows, 401 with WWW-Authenticate, '
              '405 with Allow, 429 with Retry-After. Learn the five classes and the dozen codes that matter.',
        template='lab/basics_status.html',
    ),
    LabSpec(
        slug='headers', group='basics', level=4,
        title='Headers & content negotiation', subtitle='Same URL, four formats',
        blurb='One endpoint answers as JSON, HTML, CSV or plain text depending on the Accept header you send, and in '
              'three languages depending on Accept-Language. Then a tour of the headers you will meet every day.',
        template='lab/basics_headers.html',
    ),
    LabSpec(
        slug='sending-data', group='basics', level=5,
        title='Sending data', subtitle='Query string, form, JSON, multipart',
        blurb='The same three fields sent four ways. See the raw body of each encoding, how big it is, how the server '
              'parses it, and why a file upload needs multipart.',
        template='lab/basics_data.html',
    ),

    LabSpec(
        slug='short-polling', group='realtime', level=6,
        title='Short polling', subtitle='Ask again. And again.',
        blurb='The browser asks "anything new?" on a fixed timer. Simple and works everywhere, '
              'but most requests come back empty — watch the counter climb while the data stands still.',
        template='lab/realtime.html',
    ),
    LabSpec(
        slug='long-polling', group='realtime', level=7,
        title='Long polling', subtitle='Ask once, wait for an answer',
        blurb='The server holds the request open until something happens (or a timeout), then the '
              'browser immediately asks again. Same API shape as polling, a fraction of the requests.',
        template='lab/realtime.html',
    ),
    LabSpec(
        slug='sse', group='realtime', level=8,
        title='Server-Sent Events', subtitle='One request, many events',
        blurb='A single HTTP response that never ends; the server writes an event whenever it has one. '
              'Built into browsers as EventSource, reconnects on its own and can replay what you missed.',
        template='lab/realtime.html',
    ),
    LabSpec(
        slug='websocket', group='realtime', level=9,
        title='WebSockets', subtitle='Both directions, one connection',
        blurb='HTTP upgrades to a persistent two-way socket. The only option here where the browser can '
              'push too — type a message and every other open tab sees it.',
        template='lab/realtime.html',
    ),
    LabSpec(
        slug='compare', group='realtime', level=10,
        title='Side by side', subtitle='All four against the same feed',
        blurb='The same live ticker delivered four ways at once. Compare requests, bytes and latency, then '
              'simulate an outage and watch how each one recovers.',
        template='lab/compare.html',
    ),

    # --- HTTP ---------------------------------------------------------------
    LabSpec(
        slug='caching', group='http', level=11,
        title='Caching & ETags', subtitle='The fastest request is the one you skip',
        blurb='Three ways to serve the same document: never cache it, revalidate it with an ETag (a 304 '
              'and zero bytes when nothing changed), or let the browser keep it for ten seconds without asking.',
        template='lab/http_cache.html',
    ),
    LabSpec(
        slug='compression', group='http', level=12,
        title='Compression', subtitle='gzip, brotli, and what they cost',
        blurb='The same 170 KB JSON with identity, gzip and brotli encoding. The browser decompresses '
              'transparently; the Resource Timing API shows what actually crossed the wire.',
        template='lab/http_compress.html',
    ),
    LabSpec(
        slug='range-requests', group='http', level=13,
        title='Range requests', subtitle='Pause, resume, verify',
        blurb='A 5 MB download fetched in byte ranges. Pause it, resume from where it stopped, and prove '
              'the reassembled file is intact by hashing it in the browser.',
        template='lab/http_range.html',
    ),
    LabSpec(
        slug='streaming', group='http', level=14,
        title='Streaming responses', subtitle='Chunked transfer vs buffered',
        blurb='Twenty results that each take 200 ms to produce. Buffered, you stare at nothing for four '
              'seconds; streamed, they appear as they happen. Same total time, very different experience.',
        template='lab/http_stream.html',
    ),
    LabSpec(
        slug='cors', group='http', level=15,
        title='CORS', subtitle='Why the browser blocked your fetch',
        blurb='This page calls the same server through a different origin and toggles the CORS headers. '
              'See preflights, watch requests reach the server yet stay unreadable, and fix it one header at a time.',
        template='lab/http_cors.html',
    ),

    # --- Server patterns ------------------------------------------------------
    LabSpec(
        slug='background-jobs', group='server', level=16,
        title='Background jobs', subtitle='202 Accepted, then progress',
        blurb='A request that takes ten seconds should not hold the connection for ten seconds. Start a job, '
              'get a 202 and a status URL back immediately, then follow its progress by polling or SSE — and cancel it.',
        template='lab/srv_jobs.html',
    ),
    LabSpec(
        slug='rate-limiting', group='server', level=17,
        title='Rate limiting', subtitle='Token bucket vs sliding window',
        blurb='Spam an endpoint and hit 429 Too Many Requests with a Retry-After. Watch a token bucket refill '
              'and a sliding window slide, and see why they feel different to a client.',
        template='lab/srv_ratelimit.html',
    ),
    LabSpec(
        slug='idempotency', group='server', level=18,
        title='Idempotency keys', subtitle='Double-click a payment safely',
        blurb='The bank is slow, so the user clicks Pay twice. Without a key you charge them twice; with one, '
              'the second request is recognised and the first result replayed.',
        template='lab/srv_idempotency.html',
    ),
    LabSpec(
        slug='webhooks', group='server', level=19,
        title='Webhooks', subtitle='Signed, retried, verified',
        blurb='This server delivers an event to a URL like Stripe or GitHub would: HMAC-signed, with exponential '
              'retries. A receiver on the same machine verifies the signature — break it, or make the receiver fail, and watch.',
        template='lab/srv_webhooks.html',
    ),
    LabSpec(
        slug='cancellation', group='server', level=20,
        title='Debounce & cancellation', subtitle='Search-as-you-type done right',
        blurb='A search box against a jittery API. Naively, old responses overwrite new ones. Debounce cuts the '
              'requests; AbortController makes the stale ones disappear entirely.',
        template='lab/srv_cancel.html',
    ),

    # --- Auth & sessions ------------------------------------------------------
    LabSpec(
        slug='sessions-vs-jwt', group='auth', level=21,
        title='Cookie sessions vs JWT', subtitle='Where does the truth live?',
        blurb='Log in both ways. A session is an id in an HttpOnly cookie pointing at facts on the server; a JWT is '
              'the facts themselves, signed. Inspect both, tamper with the token, then revoke everything and see which one dies.',
        template='lab/auth_sessions.html',
    ),
    LabSpec(
        slug='csrf', group='auth', level=22,
        title='CSRF', subtitle='Your cookie, their form',
        blurb='A malicious page submits a form to this app while you are logged in, and the browser helpfully attaches '
              'your session cookie. Watch your email change. Then turn on the token and watch it fail.',
        template='lab/auth_csrf.html',
    ),
    LabSpec(
        slug='oauth', group='auth', level=23,
        title='OAuth 2 & OpenID Connect', subtitle='"Log in with…", every hop visible',
        blurb='The authorization-code flow with PKCE against a fake identity provider hosted right here. Every redirect, '
              'the back-channel token exchange, the id_token checks — logged step by step. Then break it on purpose.',
        template='lab/auth_oauth.html',
    ),
    LabSpec(
        slug='totp', group='auth', level=24,
        title='Two-factor (TOTP)', subtitle='The six digits, explained',
        blurb='Enrol with a real authenticator app by scanning a QR code, then verify. See the counter, the HMAC, '
              'the 30-second window, why one step of clock drift is tolerated, and why a code can only be used once.',
        template='lab/auth_totp.html',
    ),

    # --- Browser platform -----------------------------------------------------
    LabSpec(
        slug='web-workers', group='browser', level=25,
        title='Web Workers', subtitle='Get off the main thread',
        blurb='Run a heavy computation on the main thread and watch the page freeze — the spinner stops, clicks queue up. '
              'Run the same work in a worker and everything keeps moving.',
        template='lab/br_workers.html',
    ),
    LabSpec(
        slug='offline', group='browser', level=26,
        title='Service Worker & offline', subtitle='A proxy that lives in the browser',
        blurb='Install a service worker, then cut the network in DevTools. The page still loads. Compare cache-first, '
              'network-first and stale-while-revalidate against a slow API, request by request.',
        template='lab/br_offline.html',
    ),
    LabSpec(
        slug='webrtc', group='browser', level=27,
        title='WebRTC', subtitle='Peer to peer — the server only introduces you',
        blurb='Video between two tabs. The server relays a handful of small signalling messages over a WebSocket; '
              'the media itself flows directly between the peers and never touches the server. The stats prove it.',
        template='lab/br_webrtc.html',
    ),
    LabSpec(
        slug='wasm', group='browser', level=28,
        title='WebAssembly', subtitle='The same loop, compiled',
        blurb='A Mandelbrot kernel in JavaScript and as a 300-byte hand-assembled WebAssembly module, rendering the '
              'same image and timed side by side. Includes the honest part: when Wasm helps and when the JIT already won.',
        template='lab/br_wasm.html',
    ),
    LabSpec(
        slug='push', group='browser', level=29,
        title='Push notifications', subtitle='Reach a tab that is closed',
        blurb='Subscribe, close the tab, have the server send a notification — via the browser vendor\'s push service, '
              'end-to-end encrypted, authenticated with VAPID. Needs internet access to that push service.',
        template='lab/br_push.html',
    ),

    # --- Data layer -----------------------------------------------------------
    LabSpec(
        slug='locking', group='data', level=30,
        title='Lost updates & locking', subtitle='Two people, one row',
        blurb='Two editors load the same account, both change it, both save. With no protection the first save '
              'silently vanishes. Optimistic locking catches it with a version column; pessimistic locking prevents it with a lease.',
        template='lab/data_locking.html',
    ),
    LabSpec(
        slug='n-plus-one', group='data', level=31,
        title='The N+1 problem', subtitle='One query becomes thirty-one',
        blurb='Load 30 authors and their books. Lazily, that is 1 + 30 queries — one per author, fired from inside the loop. '
              'Switch the loading strategy and watch the count drop to 2, then 1. Every statement is shown.',
        template='lab/data_nplusone.html',
    ),
    LabSpec(
        slug='pagination', group='data', level=32,
        title='Offset vs cursor pagination', subtitle='Page 2 while the data moves',
        blurb='Page through 200 items both ways. Then have "someone else" insert a row while you are on page 2: '
              'offset pagination shows you a duplicate, cursor pagination does not. See why, in the SQL.',
        template='lab/data_pagination.html',
    ),
    LabSpec(
        slug='migrations', group='data', level=33,
        title='Zero-downtime migration', subtitle='Expand, backfill, contract',
        blurb='Add a required column to a table that is being read and written every second, without anything failing. '
              'Three steps in the right order, with the traffic running the whole time.',
        template='lab/data_migration.html',
    ),
]

LABS_BY_SLUG = {spec.slug: spec for spec in LABS}


def labs_by_group():
    grouped = []
    for key, title, description in LAB_GROUPS:
        specs = sorted((s for s in LABS if s.group == key), key=lambda s: s.level)
        if specs:
            grouped.append((key, title, description, specs))
    return grouped
