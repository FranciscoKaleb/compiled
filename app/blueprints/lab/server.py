"""Level 3 — server-side patterns: jobs, rate limits, idempotency, webhooks, cancellation.

    POST /lab/api/server/jobs                      start a slow job     -> {job_id}
    GET  /lab/api/server/jobs/<id>                 its state (for polling)
    GET  /lab/api/server/jobs/<id>/events          the same, as SSE
    POST /lab/api/server/jobs/<id>/cancel
    GET  /lab/api/server/limited?algo=bucket|window|none     a rate-limited endpoint
    GET  /lab/api/server/limited/state             what the limiter currently holds
    POST /lab/api/server/pay                       charge; honours Idempotency-Key
    GET  /lab/api/server/pay/ledger                every charge recorded
    POST /lab/api/server/webhooks/send             deliver a signed event to a URL, with retries
    *    /lab/api/server/webhooks/inbox            a receiver you can point it at (toggle failures)
    GET  /lab/api/server/webhooks/log              deliveries + receipts
    GET  /lab/api/server/search?q=                 slow, jittery search for the cancellation demo
"""
import collections
import hashlib
import hmac
import json
import random
import secrets
import threading
import time
import uuid

import urllib.error
import urllib.request

from flask import Response, jsonify, request, stream_with_context

from app.blueprints.lab import bp

# ---------------------------------------------------------------------------
# 12. Background jobs with progress
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Condition()
JOB_STEPS = 20


def _job_worker(job_id: str, steps: int, fail_at: int | None):
    for step in range(1, steps + 1):
        time.sleep(random.uniform(0.15, 0.45))
        with _jobs_lock:
            job = _jobs[job_id]
            if job['status'] == 'cancelled':
                job['finished_ms'] = int(time.time() * 1000)
                _jobs_lock.notify_all()
                return
            if fail_at and step == fail_at:
                job.update(status='failed', error=f'step {step} threw an exception', finished_ms=int(time.time() * 1000))
                _jobs_lock.notify_all()
                return
            job.update(progress=step, message=f'processed chunk {step} of {steps}', status='running')
            _jobs_lock.notify_all()
    with _jobs_lock:
        _jobs[job_id].update(status='done', result={'rows': steps * 1234, 'checksum': secrets.token_hex(4)},
                             finished_ms=int(time.time() * 1000))
        _jobs_lock.notify_all()


@bp.post('/api/server/jobs', endpoint='api_srv_job_start')
def job_start():
    data = request.get_json(silent=True) or {}
    steps = max(3, min(60, int(data.get('steps', JOB_STEPS))))
    fail_at = int(data['fail_at']) if data.get('fail_at') else None
    job_id = uuid.uuid4().hex[:10]
    with _jobs_lock:
        # Keep the table small; this is a demo, not a queue.
        for old in [k for k, v in _jobs.items() if v.get('finished_ms') and time.time() * 1000 - v['finished_ms'] > 600_000]:
            del _jobs[old]
        _jobs[job_id] = {'id': job_id, 'status': 'queued', 'progress': 0, 'total': steps,
                         'message': 'waiting for a worker', 'started_ms': int(time.time() * 1000)}
    threading.Thread(target=_job_worker, args=(job_id, steps, fail_at), daemon=True).start()
    # 202 Accepted + Location is the textbook answer to "this will take a while".
    response = jsonify({'ok': True, 'job_id': job_id, 'status_url': f'/lab/api/server/jobs/{job_id}'})
    response.status_code = 202
    response.headers['Location'] = f'/lab/api/server/jobs/{job_id}'
    return response


@bp.get('/api/server/jobs/<job_id>', endpoint='api_srv_job_status')
def job_status(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        snapshot = dict(job) if job else None
    if snapshot is None:
        return jsonify({'ok': False, 'error': 'unknown job'}), 404
    return jsonify({'ok': True, 'job': snapshot})


@bp.get('/api/server/jobs/<job_id>/events', endpoint='api_srv_job_events')
def job_events(job_id):
    def generate():
        last = None
        while True:
            with _jobs_lock:
                job = _jobs.get(job_id)
                snapshot = dict(job) if job else None
                if snapshot == last:
                    _jobs_lock.wait(timeout=1.0)
                    continue
            if snapshot is None:
                yield 'event: error\ndata: {"error": "unknown job"}\n\n'
                return
            last = snapshot
            yield f"event: progress\ndata: {json.dumps(snapshot)}\n\n"
            if snapshot['status'] in ('done', 'failed', 'cancelled'):
                return
    return Response(stream_with_context(generate()), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@bp.post('/api/server/jobs/<job_id>/cancel', endpoint='api_srv_job_cancel')
def job_cancel(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return jsonify({'ok': False, 'error': 'unknown job'}), 404
        if job['status'] in ('queued', 'running'):
            job.update(status='cancelled', message='cancelled by user')
            _jobs_lock.notify_all()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# 13. Rate limiting: token bucket vs sliding window
# ---------------------------------------------------------------------------

BUCKET_CAPACITY = 5
BUCKET_REFILL_PER_S = 1.0
WINDOW_LIMIT = 5
WINDOW_SECONDS = 5.0

_rl_lock = threading.Lock()
_bucket = {'tokens': float(BUCKET_CAPACITY), 'updated': time.time()}
_window: collections.deque = collections.deque()


def _bucket_take() -> tuple[bool, float, float]:
    """(allowed, tokens_left, seconds_until_next_token)"""
    now = time.time()
    _bucket['tokens'] = min(BUCKET_CAPACITY, _bucket['tokens'] + (now - _bucket['updated']) * BUCKET_REFILL_PER_S)
    _bucket['updated'] = now
    if _bucket['tokens'] >= 1:
        _bucket['tokens'] -= 1
        return True, _bucket['tokens'], 0.0
    return False, _bucket['tokens'], (1 - _bucket['tokens']) / BUCKET_REFILL_PER_S


def _window_take() -> tuple[bool, int, float]:
    """(allowed, used_in_window, seconds_until_oldest_expires)"""
    now = time.time()
    while _window and _window[0] <= now - WINDOW_SECONDS:
        _window.popleft()
    if len(_window) < WINDOW_LIMIT:
        _window.append(now)
        return True, len(_window), 0.0
    return False, len(_window), _window[0] + WINDOW_SECONDS - now


@bp.get('/api/server/limited', endpoint='api_srv_limited')
def limited():
    algo = request.args.get('algo', 'bucket')
    with _rl_lock:
        if algo == 'window':
            allowed, used, wait = _window_take()
            remaining = max(0, WINDOW_LIMIT - used)
            limit_header = f'{WINDOW_LIMIT};w={int(WINDOW_SECONDS)}'
        elif algo == 'none':
            allowed, remaining, wait, limit_header = True, None, 0.0, None
        else:
            allowed, tokens, wait = _bucket_take()
            remaining = int(tokens)
            limit_header = f'{BUCKET_CAPACITY};refill={BUCKET_REFILL_PER_S}/s'

    if allowed:
        response = jsonify({'ok': True, 'message': 'served', 'algo': algo})
    else:
        response = jsonify({'ok': False, 'error': 'Too many requests', 'algo': algo, 'retry_after_s': round(wait, 2)})
        response.status_code = 429
        response.headers['Retry-After'] = str(max(1, int(wait + 0.999)))
    if limit_header:
        # The IETF draft header names; many APIs use X-RateLimit-* instead.
        response.headers['RateLimit-Limit'] = limit_header
        response.headers['RateLimit-Remaining'] = str(remaining)
        response.headers['RateLimit-Reset'] = str(int(wait + 0.999)) if not allowed else '0'
    return response


@bp.get('/api/server/limited/state', endpoint='api_srv_limited_state')
def limited_state():
    with _rl_lock:
        now = time.time()
        tokens = min(BUCKET_CAPACITY, _bucket['tokens'] + (now - _bucket['updated']) * BUCKET_REFILL_PER_S)
        while _window and _window[0] <= now - WINDOW_SECONDS:
            _window.popleft()
        stamps = [round(now - t, 2) for t in _window]
    return jsonify({'ok': True,
                    'bucket': {'tokens': round(tokens, 2), 'capacity': BUCKET_CAPACITY, 'refill_per_s': BUCKET_REFILL_PER_S},
                    'window': {'used': len(stamps), 'limit': WINDOW_LIMIT, 'seconds': WINDOW_SECONDS, 'ages': stamps}})


@bp.post('/api/server/limited/reset', endpoint='api_srv_limited_reset')
def limited_reset():
    with _rl_lock:
        _bucket.update(tokens=float(BUCKET_CAPACITY), updated=time.time())
        _window.clear()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# 14. Idempotency keys
# ---------------------------------------------------------------------------

_pay_lock = threading.Lock()
_ledger: list[dict] = []
_idempotency: dict[str, dict] = {}       # key -> stored response


@bp.post('/api/server/pay', endpoint='api_srv_pay')
def pay():
    data = request.get_json(silent=True) or {}
    amount = float(data.get('amount', 25))
    key = request.headers.get('Idempotency-Key')
    time.sleep(random.uniform(0.4, 1.2))          # the "bank" is slow — which is why people double-click

    with _pay_lock:
        if key and key in _idempotency:
            stored = _idempotency[key]
            response = jsonify({**stored, 'replayed': True})
            response.headers['Idempotent-Replayed'] = 'true'
            return response

        charge = {'charge_id': 'ch_' + secrets.token_hex(5), 'amount': amount, 'at_ms': int(time.time() * 1000),
                  'idempotency_key': key}
        _ledger.append(charge)
        del _ledger[:-50]
        body = {'ok': True, 'charge': charge, 'replayed': False}
        if key:
            _idempotency[key] = body
            if len(_idempotency) > 500:
                _idempotency.pop(next(iter(_idempotency)))
    return jsonify(body)


@bp.get('/api/server/pay/ledger', endpoint='api_srv_ledger')
def ledger():
    with _pay_lock:
        rows = list(reversed(_ledger))
        total = sum(c['amount'] for c in _ledger)
    return jsonify({'ok': True, 'charges': rows, 'total': round(total, 2), 'count': len(rows)})


@bp.post('/api/server/pay/reset', endpoint='api_srv_ledger_reset')
def ledger_reset():
    with _pay_lock:
        _ledger.clear()
        _idempotency.clear()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# 15. Webhooks: signed delivery with retries, and a receiver to point them at
# ---------------------------------------------------------------------------

WEBHOOK_SECRET = 'whsec_demo_' + hashlib.sha256(b'compiled-lab').hexdigest()[:24]
RETRY_SCHEDULE = [0, 1, 2, 4]            # seconds between attempts

_wh_lock = threading.Lock()
_deliveries: list[dict] = []             # what we sent, attempt by attempt
_inbox: list[dict] = []                  # what the receiver got
_inbox_mode = {'fail': False, 'slow': False}


def _sign(secret: str, timestamp: int, body: bytes) -> str:
    """Stripe-style: HMAC-SHA256 over "<timestamp>.<raw body>"."""
    mac = hmac.new(secret.encode(), f'{timestamp}.'.encode() + body, hashlib.sha256)
    return 't=' + str(timestamp) + ',v1=' + mac.hexdigest()


def _deliver(delivery_id: str, url: str, body: bytes, secret: str):
    for attempt, delay in enumerate(RETRY_SCHEDULE, start=1):
        if delay:
            time.sleep(delay)
        timestamp = int(time.time())
        headers = {'Content-Type': 'application/json', 'User-Agent': 'CompiledWebhooks/1.0',
                   'X-Webhook-Id': delivery_id, 'X-Webhook-Attempt': str(attempt),
                   'X-Webhook-Signature': _sign(secret, timestamp, body)}
        started = time.time()
        record = {'delivery_id': delivery_id, 'attempt': attempt, 'url': url, 'at_ms': int(started * 1000)}
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=3) as resp:
                record.update(status=resp.status, ms=int((time.time() - started) * 1000), outcome='delivered')
            with _wh_lock:
                _deliveries.append(record)
            return
        except urllib.error.HTTPError as exc:
            record.update(status=exc.code, ms=int((time.time() - started) * 1000),
                          outcome='retrying' if attempt < len(RETRY_SCHEDULE) else 'gave up')
        except Exception as exc:
            record.update(status=None, error=type(exc).__name__, ms=int((time.time() - started) * 1000),
                          outcome='retrying' if attempt < len(RETRY_SCHEDULE) else 'gave up')
        with _wh_lock:
            _deliveries.append(record)
            del _deliveries[:-100]


@bp.post('/api/server/webhooks/send', endpoint='api_srv_wh_send')
def webhook_send():
    data = request.get_json(silent=True) or {}
    url = (data.get('url') or (request.host_url.rstrip('/') + '/lab/api/server/webhooks/inbox')).strip()
    if not url.startswith(('http://127.0.0.1', 'http://localhost', request.host_url)):
        # Never let a demo page turn the server into an open relay.
        return jsonify({'ok': False, 'error': 'For safety this demo only delivers to this machine.'}), 400
    secret = data.get('secret') or WEBHOOK_SECRET
    event = {'id': 'evt_' + secrets.token_hex(6), 'type': data.get('type', 'order.paid'),
             'created': int(time.time()), 'data': {'order_id': random.randint(1000, 9999), 'amount': 42.0}}
    body = json.dumps(event).encode()
    delivery_id = 'dlv_' + secrets.token_hex(4)
    threading.Thread(target=_deliver, args=(delivery_id, url, body, secret), daemon=True).start()
    return jsonify({'ok': True, 'delivery_id': delivery_id, 'event': event})


@bp.route('/api/server/webhooks/inbox', methods=['POST'], endpoint='api_srv_wh_inbox')
def webhook_inbox():
    """The receiver. Verifies the signature the way a real integration should."""
    body = request.get_data()
    header = request.headers.get('X-Webhook-Signature', '')
    parts = dict(p.split('=', 1) for p in header.split(',') if '=' in p)
    verdict, reason = False, 'no signature'
    try:
        ts = int(parts.get('t', '0'))
        expected = _sign(WEBHOOK_SECRET, ts, body).split('v1=')[1]
        if abs(time.time() - ts) > 300:
            reason = 'timestamp too old (replay?)'
        elif hmac.compare_digest(expected, parts.get('v1', '')):
            verdict, reason = True, 'valid'
        else:
            reason = 'signature mismatch — wrong secret or tampered body'
    except (ValueError, IndexError):
        reason = 'malformed signature header'

    with _wh_lock:
        mode = dict(_inbox_mode)
    if mode['slow']:
        time.sleep(4)                                   # longer than the sender's timeout
    receipt = {'at_ms': int(time.time() * 1000), 'delivery_id': request.headers.get('X-Webhook-Id'),
               'attempt': request.headers.get('X-Webhook-Attempt'), 'verified': verdict, 'reason': reason,
               'event_type': (json.loads(body or b'{}')).get('type'), 'body_bytes': len(body)}
    if mode['fail']:
        receipt['responded'] = 500
        with _wh_lock:
            _inbox.append(receipt); del _inbox[:-100]
        return jsonify({'ok': False, 'error': 'receiver is pretending to be broken'}), 500
    if not verdict:
        receipt['responded'] = 401
        with _wh_lock:
            _inbox.append(receipt); del _inbox[:-100]
        return jsonify({'ok': False, 'error': reason}), 401
    receipt['responded'] = 200
    with _wh_lock:
        _inbox.append(receipt); del _inbox[:-100]
    return jsonify({'ok': True, 'received': True})


@bp.post('/api/server/webhooks/inbox/mode', endpoint='api_srv_wh_mode')
def webhook_mode():
    data = request.get_json(silent=True) or {}
    with _wh_lock:
        _inbox_mode['fail'] = bool(data.get('fail', _inbox_mode['fail']))
        _inbox_mode['slow'] = bool(data.get('slow', _inbox_mode['slow']))
        mode = dict(_inbox_mode)
    return jsonify({'ok': True, 'mode': mode})


@bp.get('/api/server/webhooks/log', endpoint='api_srv_wh_log')
def webhook_log():
    with _wh_lock:
        return jsonify({'ok': True, 'deliveries': list(reversed(_deliveries))[:40], 'inbox': list(reversed(_inbox))[:40],
                        'mode': dict(_inbox_mode), 'secret': WEBHOOK_SECRET})


@bp.post('/api/server/webhooks/reset', endpoint='api_srv_wh_reset')
def webhook_reset():
    with _wh_lock:
        _deliveries.clear(); _inbox.clear()
        _inbox_mode.update(fail=False, slow=False)
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# 16. Debounce / throttle / cancellation: a deliberately jittery search
# ---------------------------------------------------------------------------

_WORDS = ('apple apricot avocado banana blueberry blackberry cherry coconut cranberry date dragonfruit '
          'elderberry fig grape grapefruit guava honeydew jackfruit kiwi kumquat lemon lime lychee mango '
          'melon mulberry nectarine orange papaya passionfruit peach pear persimmon pineapple plum '
          'pomegranate quince raspberry strawberry tangerine watermelon').split()

_search_hits = {'count': 0}
_search_lock = threading.Lock()


@bp.get('/api/server/search', endpoint='api_srv_search')
def search():
    q = (request.args.get('q') or '').strip().lower()
    with _search_lock:
        _search_hits['count'] += 1
        n = _search_hits['count']
    # Random latency is the point: responses come back out of order.
    delay = random.uniform(0.2, 1.4)
    time.sleep(delay)
    results = [w for w in _WORDS if q and q in w][:8]
    return jsonify({'ok': True, 'q': q, 'results': results, 'took_ms': int(delay * 1000), 'server_hits': n})


@bp.post('/api/server/search/reset', endpoint='api_srv_search_reset')
def search_reset():
    with _search_lock:
        _search_hits['count'] = 0
    return jsonify({'ok': True})
