"""One live feed, four delivery mechanisms.

A background thread ticks a fake stock price about once a second and appends an
event to a ring buffer. Every transport below reads from that same buffer, so
the comparison page is fair: identical data, only the delivery differs.

    GET  /lab/api/ticker/poll                short polling: current state, always answers
    GET  /lab/api/ticker/long?since=<seq>    long polling: blocks until seq advances or timeout
    GET  /lab/api/ticker/sse                 server-sent events, honours Last-Event-ID
    WS   /lab/api/ticker/ws                  websocket: pushes events, broadcasts chat
    POST /lab/api/ticker/outage              simulate the server going away for N seconds
"""
import collections
import json
import random
import threading
import time

from flask import Response, current_app, jsonify, request, stream_with_context

from app.blueprints.lab import bp
from app.core.errors import AppError

BUFFER = 200                # events kept for SSE replay
TICK_SECONDS = 1.0
LONG_POLL_TIMEOUT = 25.0    # under most proxies' 30 s idle cut-off
SSE_KEEPALIVE = 15.0

_lock = threading.Condition()
_events: collections.deque = collections.deque(maxlen=BUFFER)
_seq = 0
_price = 100.0
_outage_until = 0.0
_started = False

# WebSocket clients, for chat broadcast. Guarded by _ws_lock.
_ws_lock = threading.Lock()
_ws_clients: set = set()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _push(kind: str, **payload) -> dict:
    """Append an event and wake every long-poller / SSE stream."""
    global _seq
    with _lock:
        _seq += 1
        event = {'seq': _seq, 'kind': kind, 'server_ms': _now_ms(), **payload}
        _events.append(event)
        _lock.notify_all()
    _ws_broadcast(event)
    return event


def _tick_forever():
    global _price
    while True:
        time.sleep(TICK_SECONDS + random.uniform(-0.3, 0.6))
        if in_outage():
            continue
        _price = max(1.0, _price * (1 + random.gauss(0, 0.004)))
        _push('tick', symbol='CMPL', price=round(_price, 2))


def ensure_started():
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_tick_forever, name='lab-ticker', daemon=True).start()


def in_outage() -> bool:
    return time.time() < _outage_until


def _latest() -> dict:
    with _lock:
        return dict(_events[-1]) if _events else {'seq': 0, 'kind': 'tick', 'symbol': 'CMPL', 'price': _price, 'server_ms': _now_ms()}


def _since(seq: int) -> list[dict]:
    with _lock:
        return [dict(e) for e in _events if e['seq'] > seq]


def _outage_response():
    retry = max(1, int(_outage_until - time.time()))
    response = jsonify({'ok': False, 'error': 'Simulated outage', 'retry_after': retry})
    response.status_code = 503
    response.headers['Retry-After'] = str(retry)
    return response


# ---------------------------------------------------------------------------
# 1. Short polling
# ---------------------------------------------------------------------------

@bp.get('/api/ticker/poll', endpoint='api_poll')
def poll():
    ensure_started()
    if in_outage():
        return _outage_response()
    since = request.args.get('since', type=int)
    latest = _latest()
    # `changed` lets the client count how many answers were actually useful.
    changed = since is None or latest['seq'] > since
    return jsonify({'ok': True, 'changed': changed, 'event': latest, 'seq': latest['seq']})


# ---------------------------------------------------------------------------
# 2. Long polling
# ---------------------------------------------------------------------------

@bp.get('/api/ticker/long', endpoint='api_long_poll')
def long_poll():
    ensure_started()
    if in_outage():
        return _outage_response()
    since = request.args.get('since', 0, type=int)
    deadline = time.time() + LONG_POLL_TIMEOUT

    with _lock:
        while _seq <= since:
            remaining = deadline - time.time()
            if remaining <= 0:
                # Nothing happened: answer anyway so the client can re-ask.
                return jsonify({'ok': True, 'changed': False, 'events': [], 'seq': since, 'timeout': True})
            _lock.wait(timeout=min(remaining, 1.0))
            if in_outage():
                return _outage_response()
        events = [dict(e) for e in _events if e['seq'] > since]
    return jsonify({'ok': True, 'changed': True, 'events': events, 'seq': events[-1]['seq']})


# ---------------------------------------------------------------------------
# 3. Server-Sent Events
# ---------------------------------------------------------------------------

def _sse(event: dict) -> str:
    return f"id: {event['seq']}\nevent: {event['kind']}\ndata: {json.dumps(event)}\n\n"


@bp.get('/api/ticker/sse', endpoint='api_sse')
def sse():
    ensure_started()
    if in_outage():
        return _outage_response()

    # The browser resends the id of the last event it saw when it reconnects,
    # so a dropped connection loses nothing that is still in the buffer.
    last_id = request.headers.get('Last-Event-ID') or request.args.get('since')
    try:
        cursor = int(last_id) if last_id else _latest()['seq']
    except ValueError:
        cursor = 0

    def generate():
        nonlocal cursor
        yield f"retry: 2000\n: connected, replaying from {cursor}\n\n"
        for event in _since(cursor):
            cursor = event['seq']
            yield _sse(event)

        last_beat = time.time()
        while True:
            with _lock:
                if _seq <= cursor:
                    _lock.wait(timeout=1.0)
                pending = [dict(e) for e in _events if e['seq'] > cursor]
            if in_outage():
                yield "event: outage\ndata: {\"message\": \"server going away\"}\n\n"
                return                                # closing makes EventSource reconnect
            for event in pending:
                cursor = event['seq']
                yield _sse(event)
                last_beat = time.time()
            if time.time() - last_beat > SSE_KEEPALIVE:
                yield ": keep-alive\n\n"              # a comment line; keeps proxies from timing out
                last_beat = time.time()

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ---------------------------------------------------------------------------
# 4. WebSockets
# ---------------------------------------------------------------------------

def _ws_broadcast(event: dict) -> None:
    payload = json.dumps(event)
    with _ws_lock:
        clients = list(_ws_clients)
    for ws in clients:
        try:
            ws.send(payload)
        except Exception:
            with _ws_lock:
                _ws_clients.discard(ws)


def register_websocket(sock):
    """Called from create_app once flask-sock is initialised."""

    @sock.route('/lab/api/ticker/ws')
    def ticker_ws(ws):
        ensure_started()
        if in_outage():
            ws.close(reason=1013, message='simulated outage')      # 1013 = try again later
            return

        with _ws_lock:
            _ws_clients.add(ws)
            count = len(_ws_clients)
        try:
            ws.send(json.dumps({'kind': 'hello', 'seq': _latest()['seq'], 'clients': count,
                                'server_ms': _now_ms()}))
            _ws_broadcast({'kind': 'presence', 'seq': _latest()['seq'], 'clients': count, 'server_ms': _now_ms()})

            while True:
                # Block for incoming messages; a timeout lets us notice outages.
                message = ws.receive(timeout=1.0)
                if in_outage():
                    ws.close(reason=1013, message='simulated outage')
                    return
                if message is None:
                    continue
                try:
                    data = json.loads(message)
                except ValueError:
                    data = {'type': 'chat', 'text': str(message)}

                if data.get('type') == 'ping':
                    # Round trip measurement: echo the client's timestamp back.
                    ws.send(json.dumps({'kind': 'pong', 'client_ms': data.get('client_ms'),
                                        'server_ms': _now_ms(), 'seq': _latest()['seq']}))
                elif data.get('type') == 'chat':
                    text = str(data.get('text', ''))[:280].strip()
                    if text:
                        _push('chat', text=text, sender=str(data.get('name', 'anon'))[:32])
        except Exception:
            pass
        finally:
            with _ws_lock:
                _ws_clients.discard(ws)
                count = len(_ws_clients)
            _ws_broadcast({'kind': 'presence', 'seq': _latest()['seq'], 'clients': count, 'server_ms': _now_ms()})


# ---------------------------------------------------------------------------
# Controls shared by the demo pages
# ---------------------------------------------------------------------------

@bp.post('/api/ticker/outage', endpoint='api_outage')
def outage():
    global _outage_until
    data = request.get_json(silent=True) or {}
    seconds = data.get('seconds', 8)
    try:
        seconds = max(0, min(60, int(seconds)))
    except (TypeError, ValueError):
        raise AppError('seconds must be a number between 0 and 60')
    _outage_until = time.time() + seconds
    # Wake everyone so long-pollers/SSE notice immediately rather than in 1 s.
    with _lock:
        _lock.notify_all()
    if seconds:
        with _ws_lock:
            clients = list(_ws_clients)
        for ws in clients:
            try:
                ws.close(reason=1013, message='simulated outage')
            except Exception:
                pass
    return jsonify({'ok': True, 'outage_seconds': seconds})


@bp.post('/api/ticker/publish', endpoint='api_publish')
def publish():
    """Manually inject an event — handy for showing latency on demand."""
    data = request.get_json(silent=True) or {}
    text = str(data.get('text', 'manual event'))[:120]
    event = _push('note', text=text)
    return jsonify({'ok': True, 'event': event})


@bp.get('/api/ticker/status', endpoint='api_status')
def status():
    ensure_started()
    with _ws_lock:
        ws_count = len(_ws_clients)
    return jsonify({'ok': True, 'seq': _latest()['seq'], 'buffered': len(_events),
                    'outage': in_outage(), 'ws_clients': ws_count, 'server_ms': _now_ms()})
