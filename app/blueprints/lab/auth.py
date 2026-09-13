"""Level 4 — auth & sessions: cookie sessions vs JWT, CSRF, TOTP.

Everything here is deliberately separate from the app's own Flask session so
the demos can be reset, expired and broken without touching the tools.

    POST /lab/api/auth/login            {mode: cookie|jwt, ttl}   -> cookie set, or {token}
    GET  /lab/api/auth/me               who am I (cookie or Bearer)
    POST /lab/api/auth/logout           cookie session: delete server-side
    GET  /lab/api/auth/sessions         the server-side session table
    POST /lab/api/auth/revoke-all       kill every session (the thing JWTs cannot do)
    POST /lab/api/auth/jwt/decode       split and verify a token, explaining every part

    GET/POST /lab/api/auth/profile      the CSRF victim endpoint (cookie-authenticated)
    POST /lab/api/auth/csrf/protect     {enabled} toggle the token check

    POST /lab/api/auth/totp/enrol       new secret + QR
    POST /lab/api/auth/totp/verify      {code}
    GET  /lab/api/auth/totp/peek        the server's current code and time left
"""
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from io import BytesIO

from flask import jsonify, make_response, request

from app.blueprints.lab import bp

COOKIE = 'lab_sid'
DEFAULT_TTL = 45           # short, so expiry is something you can watch happen
JWT_SECRET = 'lab-jwt-' + hashlib.sha256(b'compiled').hexdigest()[:24]

_lock = threading.Lock()
_sessions: dict[str, dict] = {}          # sid -> {user, role, created, expires, csrf}
_csrf_required = {'enabled': False}
_profiles: dict[str, dict] = {}          # user -> {email}


def _now() -> int:
    return int(time.time())


def _purge():
    now = _now()
    for sid in [s for s, v in _sessions.items() if v['expires'] <= now]:
        del _sessions[sid]


def _get_session():
    sid = request.cookies.get(COOKIE)
    if not sid:
        return None, None
    with _lock:
        _purge()
        session = _sessions.get(sid)
        return sid, (dict(session) if session else None)


# ---------------------------------------------------------------------------
# JWT by hand (HS256), so the parts are visible
# ---------------------------------------------------------------------------

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def jwt_encode(claims: dict, secret: str = JWT_SECRET) -> str:
    header = _b64(json.dumps({'alg': 'HS256', 'typ': 'JWT'}, separators=(',', ':')).encode())
    payload = _b64(json.dumps(claims, separators=(',', ':')).encode())
    signature = _b64(hmac.new(secret.encode(), f'{header}.{payload}'.encode(), hashlib.sha256).digest())
    return f'{header}.{payload}.{signature}'


def jwt_decode(token: str, secret: str = JWT_SECRET) -> dict:
    """Return a report: parts, whether the signature holds, whether it expired."""
    report = {'valid': False, 'header': None, 'payload': None, 'signature_ok': False, 'expired': None, 'error': None}
    parts = token.split('.')
    if len(parts) != 3:
        report['error'] = 'a JWT has exactly three dot-separated parts'
        return report
    try:
        report['header'] = json.loads(_unb64(parts[0]))
        report['payload'] = json.loads(_unb64(parts[1]))
    except Exception:
        report['error'] = 'header or payload is not valid base64url JSON'
        return report
    if report['header'].get('alg') != 'HS256':
        report['error'] = f"alg {report['header'].get('alg')!r} is not accepted (only HS256 here — never trust alg=none)"
        return report
    expected = _b64(hmac.new(secret.encode(), f'{parts[0]}.{parts[1]}'.encode(), hashlib.sha256).digest())
    report['signature_ok'] = hmac.compare_digest(expected, parts[2])
    if not report['signature_ok']:
        report['error'] = 'signature does not match — the payload was changed or signed with another key'
        return report
    exp = report['payload'].get('exp')
    report['expired'] = bool(exp and exp <= _now())
    if report['expired']:
        report['error'] = f"expired {_now() - exp}s ago"
        return report
    report['valid'] = True
    return report


# ---------------------------------------------------------------------------
# 17. Sessions vs JWT
# ---------------------------------------------------------------------------

@bp.post('/api/auth/login', endpoint='api_auth_login')
def login():
    data = request.get_json(silent=True) or {}
    mode = data.get('mode', 'cookie')
    ttl = max(10, min(600, int(data.get('ttl', DEFAULT_TTL))))
    user = (data.get('user') or 'alice').strip()[:32] or 'alice'
    role = 'user'

    if mode == 'jwt':
        claims = {'sub': user, 'role': role, 'iat': _now(), 'exp': _now() + ttl, 'iss': 'compiled-lab'}
        return jsonify({'ok': True, 'mode': 'jwt', 'token': jwt_encode(claims), 'claims': claims,
                        'note': 'The server stored nothing. Everything it will ever know about this login is inside the token.'})

    sid = secrets.token_urlsafe(24)
    with _lock:
        _purge()
        _sessions[sid] = {'user': user, 'role': role, 'created': _now(), 'expires': _now() + ttl,
                          'csrf': secrets.token_urlsafe(16), 'ua': request.headers.get('User-Agent', '')[:60]}
        _profiles.setdefault(user, {'email': f'{user}@example.com'})
    response = jsonify({'ok': True, 'mode': 'cookie', 'sid_preview': sid[:8] + '…',
                        'note': 'A random id went into an HttpOnly cookie; the facts live server-side.'})
    response.set_cookie(COOKIE, sid, max_age=ttl, httponly=True, samesite='Lax', path='/')
    return response


@bp.get('/api/auth/me', endpoint='api_auth_me')
def me():
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        report = jwt_decode(auth[7:])
        if not report['valid']:
            return jsonify({'ok': False, 'mode': 'jwt', 'error': report['error'], 'report': report}), 401
        return jsonify({'ok': True, 'mode': 'jwt', 'user': report['payload']['sub'], 'role': report['payload']['role'],
                        'expires_in': report['payload']['exp'] - _now(), 'report': report,
                        'note': 'Verified by recomputing the HMAC. No lookup happened.'})

    sid, session = _get_session()
    if not sid:
        return jsonify({'ok': False, 'mode': 'cookie', 'error': 'no session cookie was sent'}), 401
    if not session:
        return jsonify({'ok': False, 'mode': 'cookie', 'error': 'cookie present but no such session on the server (expired, logged out, or revoked)'}), 401
    return jsonify({'ok': True, 'mode': 'cookie', 'user': session['user'], 'role': session['role'],
                    'expires_in': session['expires'] - _now(), 'note': 'Looked up by session id in the server store.'})


@bp.post('/api/auth/logout', endpoint='api_auth_logout')
def logout():
    sid = request.cookies.get(COOKIE)
    with _lock:
        removed = _sessions.pop(sid, None) is not None if sid else False
    response = jsonify({'ok': True, 'removed': removed})
    response.delete_cookie(COOKIE, path='/')
    return response


@bp.get('/api/auth/sessions', endpoint='api_auth_sessions')
def sessions():
    with _lock:
        _purge()
        rows = [{'sid': s[:8] + '…', 'user': v['user'], 'role': v['role'], 'expires_in': v['expires'] - _now(),
                 'mine': s == request.cookies.get(COOKIE)} for s, v in _sessions.items()]
    return jsonify({'ok': True, 'sessions': rows, 'csrf_required': _csrf_required['enabled']})


@bp.post('/api/auth/revoke-all', endpoint='api_auth_revoke')
def revoke_all():
    with _lock:
        count = len(_sessions)
        _sessions.clear()
    return jsonify({'ok': True, 'revoked': count,
                    'note': 'Every cookie session is dead instantly. Any JWT already issued is still valid until its exp.'})


@bp.post('/api/auth/jwt/decode', endpoint='api_auth_jwt_decode')
def decode():
    token = (request.get_json(silent=True) or {}).get('token', '')
    return jsonify({'ok': True, 'report': jwt_decode(token)})


# ---------------------------------------------------------------------------
# 18. CSRF
# ---------------------------------------------------------------------------

@bp.route('/api/auth/profile', methods=['GET', 'POST'], endpoint='api_auth_profile')
def profile():
    sid, session = _get_session()
    if not session:
        if request.method == 'POST' and request.form:
            # A form post with no session: redirect back like a real app would.
            return make_response('<p>Not logged in.</p>', 401)
        return jsonify({'ok': False, 'error': 'log in first (Sessions page or the button on this page)'}), 401

    user = session['user']
    if request.method == 'GET':
        with _lock:
            profile_ = dict(_profiles.get(user, {}))
        return jsonify({'ok': True, 'user': user, 'profile': profile_, 'csrf_token': session['csrf'],
                        'csrf_required': _csrf_required['enabled']})

    # POST: change the email. This is the action an attacker wants to trigger.
    email = (request.form.get('email') or (request.get_json(silent=True) or {}).get('email') or '').strip()[:120]
    sent = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token') or ''
    if _csrf_required['enabled'] and not hmac.compare_digest(sent, session['csrf']):
        body = {'ok': False, 'error': 'CSRF token missing or wrong — request rejected', 'blocked': True}
        if request.form and 'text/html' in request.headers.get('Accept', ''):
            return make_response(f'<h1 style="font-family:system-ui;color:#dc2626">403 — blocked: {body["error"]}</h1>', 403)
        return jsonify(body), 403

    with _lock:
        _profiles.setdefault(user, {})['email'] = email or 'unchanged'
    if request.form and 'text/html' in request.headers.get('Accept', ''):
        return make_response(f'<h1 style="font-family:system-ui;color:#dc2626">Email changed to {email}</h1>'
                             '<p style="font-family:system-ui">This is what the victim never sees: the request came from another page.</p>', 200)
    return jsonify({'ok': True, 'profile': {'email': email}})


@bp.post('/api/auth/csrf/protect', endpoint='api_auth_csrf_protect')
def csrf_protect():
    data = request.get_json(silent=True) or {}
    _csrf_required['enabled'] = bool(data.get('enabled'))
    return jsonify({'ok': True, 'enabled': _csrf_required['enabled']})


# ---------------------------------------------------------------------------
# 20. TOTP
# ---------------------------------------------------------------------------

_totp: dict[str, dict] = {}       # sid -> {secret, verified, used_counters}


@bp.post('/api/auth/totp/enrol', endpoint='api_auth_totp_enrol')
def totp_enrol():
    import pyotp
    import qrcode

    sid = request.cookies.get('lab_totp') or secrets.token_urlsafe(12)
    secret = pyotp.random_base32()
    uri = pyotp.TOTP(secret).provisioning_uri(name='you@compiled.local', issuer_name='Compiled Web Lab')
    with _lock:
        _totp[sid] = {'secret': secret, 'verified': False, 'used': set()}
        if len(_totp) > 200:
            _totp.pop(next(iter(_totp)))

    image = qrcode.make(uri, box_size=6, border=2)
    buffer = BytesIO()
    image.save(buffer, 'PNG')
    response = jsonify({'ok': True, 'secret': secret, 'uri': uri, 'qr': base64.b64encode(buffer.getvalue()).decode(),
                        'period': 30, 'digits': 6, 'algorithm': 'SHA1'})
    response.set_cookie('lab_totp', sid, max_age=3600, httponly=True, samesite='Lax', path='/')
    return response


@bp.post('/api/auth/totp/verify', endpoint='api_auth_totp_verify')
def totp_verify():
    import pyotp

    sid = request.cookies.get('lab_totp')
    with _lock:
        record = _totp.get(sid) if sid else None
    if not record:
        return jsonify({'ok': False, 'error': 'enrol first'}), 400
    code = (request.get_json(silent=True) or {}).get('code', '').strip().replace(' ', '')
    if not (code.isdigit() and len(code) == 6):
        return jsonify({'ok': False, 'error': 'a code is six digits'}), 400

    totp = pyotp.TOTP(record['secret'])
    now = _now()
    counter = now // 30
    matched = None
    for offset in (0, -1, 1):                         # accept one step of clock drift either way
        if totp.verify(code, for_time=now + offset * 30, valid_window=0):
            matched = counter + offset
            break
    if matched is None:
        return jsonify({'ok': False, 'error': 'wrong code (or more than 30 s of clock drift)'}), 401
    with _lock:
        if matched in record['used']:
            return jsonify({'ok': False, 'error': 'that code was already used — a TOTP code is one-shot', 'replay': True}), 401
        record['used'].add(matched)
        record['verified'] = True
    return jsonify({'ok': True, 'drift_steps': matched - counter,
                    'note': 'matched' + (' the current window' if matched == counter else f' the {"previous" if matched < counter else "next"} 30 s window — clock drift tolerated')})


@bp.get('/api/auth/totp/peek', endpoint='api_auth_totp_peek')
def totp_peek():
    import pyotp

    sid = request.cookies.get('lab_totp')
    with _lock:
        record = dict(_totp.get(sid, {})) if sid else {}
    if not record:
        return jsonify({'ok': False, 'error': 'enrol first'}), 400
    totp = pyotp.TOTP(record['secret'])
    now = _now()
    return jsonify({'ok': True, 'code': totp.now(), 'seconds_left': 30 - now % 30, 'counter': now // 30,
                    'previous': totp.at(now - 30), 'next': totp.at(now + 30), 'verified': record['verified'],
                    'hmac_input': f'HMAC-SHA1(secret, counter={now // 30})'})
