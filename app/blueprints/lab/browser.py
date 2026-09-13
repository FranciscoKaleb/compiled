"""Level 5 — browser platform: service worker assets, WebRTC signalling, Web Push.

    GET  /lab/sw.js                          the service worker (served with a scope header)
    GET  /lab/api/browser/offline/time       a tiny API the offline demo caches
    WS   /lab/api/browser/rtc/ws?room=…      WebRTC signalling: relay SDP/ICE to the other peer
    GET  /lab/api/browser/push/key           VAPID public key
    POST /lab/api/browser/push/subscribe     store a PushSubscription
    POST /lab/api/browser/push/send          push a notification to every subscription
"""
import json
import threading
import time
from pathlib import Path

from flask import Response, current_app, jsonify, request, send_from_directory

from app.blueprints.lab import bp

# ---------------------------------------------------------------------------
# Service worker + offline API
# ---------------------------------------------------------------------------

@bp.get('/sw.js', endpoint='service_worker')
def service_worker():
    static_dir = Path(current_app.static_folder) / 'js'
    response = send_from_directory(static_dir, 'lab_sw.js', mimetype='application/javascript')
    # A worker may only control URLs at or below its own path; this lets
    # /lab/sw.js control /lab/offline* even though it lives under /static.
    response.headers['Service-Worker-Allowed'] = '/lab/'
    response.headers['Cache-Control'] = 'no-cache'
    return response


@bp.get('/api/browser/offline/time', endpoint='api_browser_time')
def offline_time():
    time.sleep(0.4)                                  # feel the network
    response = jsonify({'ok': True, 'server_time': time.strftime('%H:%M:%S'), 'fetched_at_ms': int(time.time() * 1000)})
    response.headers['Cache-Control'] = 'no-store'
    return response


# ---------------------------------------------------------------------------
# WebRTC signalling: the server only relays offers, answers and ICE candidates.
# ---------------------------------------------------------------------------

_rooms: dict[str, list] = {}
_rooms_lock = threading.Lock()


def register_websocket(sock):
    @sock.route('/lab/api/browser/rtc/ws')
    def rtc_ws(ws):
        room = (request.args.get('room') or 'lobby')[:40]
        with _rooms_lock:
            peers = _rooms.setdefault(room, [])
            if len(peers) >= 2:
                ws.send(json.dumps({'type': 'full', 'message': 'this room already has two peers'}))
                ws.close()
                return
            peers.append(ws)
            role = 'caller' if len(peers) == 1 else 'callee'
        ws.send(json.dumps({'type': 'role', 'role': role, 'peers': len(peers)}))
        _relay(room, ws, {'type': 'peer-joined', 'peers': len(peers)})
        try:
            while True:
                message = ws.receive()
                if message is None:
                    break
                # Opaque to the server: SDP and ICE blobs go straight to the other side.
                _relay(room, ws, json.loads(message))
        except Exception:
            pass
        finally:
            with _rooms_lock:
                if ws in _rooms.get(room, []):
                    _rooms[room].remove(ws)
                if not _rooms.get(room):
                    _rooms.pop(room, None)
            _relay(room, ws, {'type': 'peer-left'})


def _relay(room: str, sender, payload: dict) -> None:
    with _rooms_lock:
        others = [p for p in _rooms.get(room, []) if p is not sender]
    for peer in others:
        try:
            peer.send(json.dumps(payload))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Web Push
# ---------------------------------------------------------------------------

_push_lock = threading.Lock()
_subscriptions: dict[str, dict] = {}     # endpoint -> subscription json
_vapid: dict | None = None


def _vapid_keys() -> dict:
    """VAPID keypair, persisted so subscriptions survive a restart."""
    global _vapid
    if _vapid:
        return _vapid
    path = Path(current_app.config['DB_DIR']) / 'vapid.json'
    if path.is_file():
        _vapid = json.loads(path.read_text())
        return _vapid
    from py_vapid import Vapid, b64urlencode
    from cryptography.hazmat.primitives import serialization
    vapid = Vapid()
    vapid.generate_keys()
    private_pem = vapid.private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    public_raw = vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    _vapid = {'private_pem': private_pem, 'public_key': b64urlencode(public_raw)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_vapid))
    return _vapid


@bp.get('/api/browser/push/key', endpoint='api_browser_push_key')
def push_key():
    try:
        keys = _vapid_keys()
    except ImportError:
        return jsonify({'ok': False, 'error': 'pywebpush is not installed on the server'}), 501
    with _push_lock:
        count = len(_subscriptions)
    return jsonify({'ok': True, 'public_key': keys['public_key'], 'subscriptions': count})


@bp.post('/api/browser/push/subscribe', endpoint='api_browser_push_subscribe')
def push_subscribe():
    sub = request.get_json(silent=True) or {}
    if not sub.get('endpoint'):
        return jsonify({'ok': False, 'error': 'not a PushSubscription'}), 400
    with _push_lock:
        _subscriptions[sub['endpoint']] = sub
        count = len(_subscriptions)
    host = sub['endpoint'].split('/')[2]
    return jsonify({'ok': True, 'subscriptions': count, 'push_service': host,
                    'note': f'The browser chose its push service ({host}); this server will POST encrypted payloads there.'})


@bp.post('/api/browser/push/unsubscribe', endpoint='api_browser_push_unsubscribe')
def push_unsubscribe():
    sub = request.get_json(silent=True) or {}
    with _push_lock:
        removed = _subscriptions.pop(sub.get('endpoint', ''), None) is not None
    return jsonify({'ok': True, 'removed': removed})


def _deliver_push(payload: str, targets: list[dict], keys: dict) -> list[dict]:
    from pywebpush import WebPushException, webpush

    results = []
    for sub in targets:
        host = sub['endpoint'].split('/')[2]
        started = time.time()
        try:
            response = webpush(subscription_info=sub, data=payload, vapid_private_key=keys['private_pem'],
                               vapid_claims={'sub': 'mailto:lab@compiled.local'}, ttl=60, timeout=10)
            results.append({'push_service': host, 'status': response.status_code, 'ms': int((time.time() - started) * 1000)})
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            results.append({'push_service': host, 'status': status, 'error': str(exc)[:160], 'ms': int((time.time() - started) * 1000)})
            if status in (404, 410):                        # subscription gone: forget it
                with _push_lock:
                    _subscriptions.pop(sub['endpoint'], None)
        except Exception as exc:
            results.append({'push_service': host, 'status': None, 'error': f'{type(exc).__name__}: {str(exc)[:120]}'})
    with _push_lock:
        _last_results['results'] = results
        _last_results['at'] = time.strftime('%H:%M:%S')
    return results


_last_results: dict = {'results': None, 'at': None}


@bp.post('/api/browser/push/send', endpoint='api_browser_push_send')
def push_send():
    try:
        import pywebpush  # noqa: F401
    except ImportError:
        return jsonify({'ok': False, 'error': 'pywebpush is not installed on the server'}), 501
    data = request.get_json(silent=True) or {}
    delay = max(0, min(120, int(data.get('delay', 0) or 0)))
    payload = json.dumps({'title': (data.get('title') or 'Compiled Web Lab')[:80],
                          'body': (data.get('body') or 'Hello from the server, delivered while the tab was closed.')[:200],
                          'url': '/lab/push', 'sent_at': time.strftime('%H:%M:%S')})
    keys = _vapid_keys()
    with _push_lock:
        targets = list(_subscriptions.values())
    if not targets:
        return jsonify({'ok': False, 'error': 'no subscriptions yet — subscribe this browser first'}), 400

    if delay:
        # The server waits, not the page — so closing the tab does not cancel it.
        def later():
            time.sleep(delay)
            _deliver_push(json.dumps({**json.loads(payload), 'sent_at': time.strftime('%H:%M:%S')}), targets, keys)
        threading.Thread(target=later, daemon=True).start()
        return jsonify({'ok': True, 'scheduled_in_s': delay, 'targets': len(targets),
                        'note': f'The server will push in {delay} s whether or not this tab is still open.'})

    results = _deliver_push(payload, targets, keys)
    return jsonify({'ok': True, 'sent': len(results), 'results': results, 'payload': json.loads(payload)})


@bp.get('/api/browser/push/last', endpoint='api_browser_push_last')
def push_last():
    with _push_lock:
        return jsonify({'ok': True, **_last_results})
