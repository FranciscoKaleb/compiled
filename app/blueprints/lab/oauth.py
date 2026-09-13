"""Level 4 — OAuth 2.0 authorization code flow with PKCE, plus an OIDC id_token.

Two parties, both hosted here so every hop is visible:

  The CLIENT (this app, "Compiled")           The IDENTITY PROVIDER ("FakeID")
  ─────────────────────────────────           ────────────────────────────────
  GET  /lab/oauth/start        ─ redirect ─▶  GET  /lab/idp/authorize   (login + consent page)
  GET  /lab/oauth/callback   ◀─ redirect ─    POST /lab/idp/approve     (user clicks Allow)
       │ backend-to-backend                   POST /lab/idp/token       (code + verifier -> tokens)
       └─────────────────────────────────▶    GET  /lab/idp/userinfo    (Bearer access_token)

Every step is appended to a per-flow log keyed by `state`, which the callback
page renders so the whole dance can be read top to bottom.
"""
import base64
import hashlib
import secrets
import threading
import time
from urllib.parse import urlencode

from flask import jsonify, redirect, render_template, request, url_for

from app.blueprints.lab import bp
from app.blueprints.lab.auth import jwt_decode, jwt_encode

CLIENT_ID = 'compiled-web-lab'
CLIENT_SECRET = 'cs_' + hashlib.sha256(b'fakeid-client').hexdigest()[:20]
IDP_KEY = 'idp-' + hashlib.sha256(b'fakeid-signing').hexdigest()[:24]
CODE_TTL = 60
TOKEN_TTL = 300

_lock = threading.RLock()   # _issue_tokens logs while holding it
_flows: dict[str, dict] = {}          # state -> {log:[], verifier, ...}
_codes: dict[str, dict] = {}          # code -> {client_id, redirect_uri, challenge, sub, used}
_access_tokens: dict[str, dict] = {}  # token -> {sub, scope, exp}

FAKE_USER = {'sub': 'u_7f3a9c', 'name': 'Alice Example', 'email': 'alice@example.com', 'picture': None}


def _log(state: str, side: str, step: str, **detail):
    with _lock:
        flow = _flows.setdefault(state, {'log': [], 'created': time.time()})
        flow['log'].append({'t': round(time.time() - flow['created'], 3), 'side': side, 'step': step, **detail})
        # keep the table small
        for old in [k for k, v in _flows.items() if time.time() - v['created'] > 900]:
            del _flows[old]


def _flow(state: str) -> dict:
    with _lock:
        return dict(_flows.get(state, {'log': []}))


# ---------------------------------------------------------------------------
# CLIENT side
# ---------------------------------------------------------------------------

@bp.get('/oauth/start', endpoint='oauth_start')
def oauth_start():
    """Step 1: build the authorization request and redirect the browser."""
    state = secrets.token_urlsafe(16)                          # binds callback to this browser
    verifier = secrets.token_urlsafe(48)                       # PKCE: kept secret by the client
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    nonce = secrets.token_urlsafe(12)                          # OIDC: bound into the id_token
    sabotage = request.args.get('sabotage', '')                # for the "what if" buttons

    with _lock:
        _flows[state] = {'log': [], 'created': time.time(), 'verifier': verifier, 'nonce': nonce, 'sabotage': sabotage}

    params = {
        'response_type': 'code', 'client_id': CLIENT_ID,
        'redirect_uri': url_for('lab.oauth_callback', _external=True),
        'scope': 'openid profile email', 'state': state,
        'code_challenge': challenge, 'code_challenge_method': 'S256', 'nonce': nonce,
    }
    if sabotage == 'redirect':
        params['redirect_uri'] = 'http://evil.example/steal'
    url = url_for('lab.idp_authorize') + '?' + urlencode(params)
    _log(state, 'client', 'Build authorization request', params={**params, 'code_challenge': challenge[:12] + '…'},
         verifier_kept_secret=verifier[:8] + '…', note='state and code_verifier are stored server-side, keyed by state')
    _log(state, 'client', 'Redirect the browser to the IdP', url=url[:160] + '…')
    return redirect(url)


@bp.get('/oauth/callback', endpoint='oauth_callback')
def oauth_callback():
    """Step 4: the IdP sent the browser back with a code. Exchange it, backend to backend."""
    state = request.args.get('state', '')
    code = request.args.get('code', '')
    error = request.args.get('error')
    flow = _flow(state)

    if error:
        _log(state, 'client', 'IdP returned an error', error=error, description=request.args.get('error_description'))
        return render_template('lab/oauth_result.html', flow=_flow(state), outcome='error', state=state)
    if not flow or 'verifier' not in flow:
        _log(state or 'unknown', 'client', 'REJECT: unknown state', note='state does not match any flow this client started — possible CSRF/login-fixation')
        return render_template('lab/oauth_result.html', flow=_flow(state or 'unknown'), outcome='error', state=state)

    _log(state, 'client', 'Callback received', code=code[:10] + '…', state_param=state[:8] + '…', note='state matched a pending flow ✓')

    verifier = flow['verifier']
    if flow.get('sabotage') == 'verifier':
        verifier = 'not-the-real-verifier'
    body = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': url_for('lab.oauth_callback', _external=True),
            'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'code_verifier': verifier}
    _log(state, 'client', 'POST /lab/idp/token  (server → server, browser never sees this)',
         body={**body, 'client_secret': 'cs_…', 'code_verifier': verifier[:8] + '…'})

    # Same process, so call the function directly instead of an HTTP round trip.
    status, tokens = _issue_tokens(body, state)
    if status != 200:
        _log(state, 'client', 'Token exchange FAILED', status=status, error=tokens)
        return render_template('lab/oauth_result.html', flow=_flow(state), outcome='error', state=state)

    _log(state, 'client', 'Tokens received', access_token=tokens['access_token'][:12] + '…', id_token='eyJ…', expires_in=tokens['expires_in'])

    id_report = jwt_decode(tokens['id_token'], IDP_KEY)
    nonce_ok = id_report['valid'] and id_report['payload'].get('nonce') == flow['nonce']
    aud_ok = id_report['valid'] and id_report['payload'].get('aud') == CLIENT_ID
    _log(state, 'client', 'Verify id_token', signature=id_report['signature_ok'], expired=id_report['expired'],
         nonce_matches=nonce_ok, audience_matches=aud_ok, claims=id_report['payload'])

    if flow.get('sabotage') == 'replay':
        status2, again = _issue_tokens(body, state)
        _log(state, 'client', 'Try the same code AGAIN (replay)', status=status2, result=again if status2 != 200 else 'issued?!')

    userinfo = _userinfo_for(tokens['access_token'])
    _log(state, 'client', 'GET /lab/idp/userinfo with Bearer access_token', response=userinfo)

    if 'error' in userinfo:
        outcome = 'revoked' if flow.get('sabotage') == 'replay' else 'error'
    else:
        outcome = 'ok' if (nonce_ok and aud_ok) else 'error'
    return render_template('lab/oauth_result.html', flow=_flow(state), outcome=outcome, state=state,
                           user=userinfo if outcome == 'ok' else None, id_token=tokens['id_token'], access_token=tokens['access_token'])


@bp.get('/oauth/flow/<state>', endpoint='oauth_flow')
def oauth_flow(state):
    return jsonify({'ok': True, 'flow': _flow(state)})


# ---------------------------------------------------------------------------
# IDENTITY PROVIDER side
# ---------------------------------------------------------------------------

@bp.get('/idp/authorize', endpoint='idp_authorize')
def idp_authorize():
    """Step 2: validate the request, then show the login/consent page."""
    a = request.args
    state = a.get('state', 'unknown')
    problems = []
    if a.get('client_id') != CLIENT_ID:
        problems.append(f"unknown client_id {a.get('client_id')!r}")
    if a.get('response_type') != 'code':
        problems.append('response_type must be "code"')
    allowed = url_for('lab.oauth_callback', _external=True)
    if a.get('redirect_uri') != allowed:
        problems.append(f"redirect_uri {a.get('redirect_uri')!r} is not registered for this client")
    if a.get('code_challenge_method') != 'S256' or not a.get('code_challenge'):
        problems.append('PKCE code_challenge (S256) is required')

    _log(state, 'idp', 'Authorization request received', client_id=a.get('client_id'), scope=a.get('scope'),
         redirect_uri=a.get('redirect_uri'), problems=problems or None)
    if problems:
        # A bad redirect_uri must NOT be redirected to — that is how codes get stolen.
        _log(state, 'idp', 'REJECTED without redirecting', reason=problems)
        return render_template('lab/idp_error.html', problems=problems, state=state), 400

    return render_template('lab/idp_consent.html', params=a, client=CLIENT_ID, user=FAKE_USER,
                           scopes=a.get('scope', '').split())


@bp.post('/idp/approve', endpoint='idp_approve')
def idp_approve():
    """Step 3: user consented. Mint a one-time code and send the browser back."""
    f = request.form
    state = f.get('state', 'unknown')
    if f.get('decision') != 'allow':
        _log(state, 'idp', 'User DENIED consent')
        return redirect(f['redirect_uri'] + '?' + urlencode({'error': 'access_denied', 'error_description': 'the user said no', 'state': state}))

    code = 'ac_' + secrets.token_urlsafe(20)
    with _lock:
        _codes[code] = {'client_id': f['client_id'], 'redirect_uri': f['redirect_uri'], 'challenge': f['code_challenge'],
                        'nonce': f.get('nonce'), 'scope': f.get('scope', ''), 'sub': FAKE_USER['sub'],
                        'expires': time.time() + CODE_TTL, 'used': False}
    _log(state, 'idp', 'User approved; authorization code minted', code=code[:10] + '…', ttl_s=CODE_TTL,
         note='the code is useless without the code_verifier that only the client holds')
    _log(state, 'idp', 'Redirect browser back to the client', to=f['redirect_uri'] + '?code=…&state=…')
    return redirect(f['redirect_uri'] + '?' + urlencode({'code': code, 'state': state}))


def _issue_tokens(body: dict, state: str) -> tuple[int, dict]:
    """The token endpoint's logic. Called directly by the client above and by the HTTP route below."""
    code = body.get('code', '')
    with _lock:
        record = _codes.get(code)
        if not record:
            _log(state, 'idp', 'Token request REJECTED', reason='unknown code')
            return 400, {'error': 'invalid_grant', 'error_description': 'unknown authorization code'}
        if record['used']:
            _log(state, 'idp', 'Token request REJECTED', reason='code already used — replay detected; revoking tokens from the first use')
            for t in [t for t, v in _access_tokens.items() if v.get('code') == code]:
                del _access_tokens[t]
            return 400, {'error': 'invalid_grant', 'error_description': 'authorization code already used'}
        if record['expires'] < time.time():
            _log(state, 'idp', 'Token request REJECTED', reason='code expired')
            return 400, {'error': 'invalid_grant', 'error_description': 'authorization code expired'}
        if body.get('client_id') != record['client_id'] or body.get('client_secret') != CLIENT_SECRET:
            _log(state, 'idp', 'Token request REJECTED', reason='client authentication failed')
            return 401, {'error': 'invalid_client'}
        if body.get('redirect_uri') != record['redirect_uri']:
            _log(state, 'idp', 'Token request REJECTED', reason='redirect_uri differs from the authorization request')
            return 400, {'error': 'invalid_grant', 'error_description': 'redirect_uri mismatch'}
        expected = base64.urlsafe_b64encode(hashlib.sha256(body.get('code_verifier', '').encode()).digest()).rstrip(b'=').decode()
        if not secrets.compare_digest(expected, record['challenge']):
            _log(state, 'idp', 'Token request REJECTED', reason='PKCE failed: SHA256(code_verifier) != code_challenge')
            return 400, {'error': 'invalid_grant', 'error_description': 'PKCE verification failed'}
        record['used'] = True

        now = int(time.time())
        access = 'at_' + secrets.token_urlsafe(24)
        _access_tokens[access] = {'sub': record['sub'], 'scope': record['scope'], 'exp': now + TOKEN_TTL, 'code': code}
        id_token = jwt_encode({'iss': 'http://fakeid.local', 'sub': record['sub'], 'aud': record['client_id'],
                               'iat': now, 'exp': now + TOKEN_TTL, 'nonce': record['nonce'],
                               'name': FAKE_USER['name'], 'email': FAKE_USER['email']}, IDP_KEY)
    _log(state, 'idp', 'Token request ACCEPTED', checks=['code unused ✓', 'not expired ✓', 'client secret ✓', 'redirect_uri ✓', 'PKCE ✓'],
         issued=['access_token (opaque, 5 min)', 'id_token (JWT signed by the IdP)'])
    return 200, {'access_token': access, 'token_type': 'Bearer', 'expires_in': TOKEN_TTL, 'id_token': id_token, 'scope': record['scope']}


@bp.post('/idp/token', endpoint='idp_token')
def idp_token():
    status, body = _issue_tokens(request.form.to_dict() or (request.get_json(silent=True) or {}), 'direct')
    return jsonify(body), status


def _userinfo_for(token: str) -> dict:
    with _lock:
        record = _access_tokens.get(token)
    if not record or record['exp'] < time.time():
        return {'error': 'invalid_token'}
    info = {'sub': record['sub']}
    if 'profile' in record['scope']:
        info['name'] = FAKE_USER['name']
    if 'email' in record['scope']:
        info['email'] = FAKE_USER['email']
    return info


@bp.get('/idp/userinfo', endpoint='idp_userinfo')
def idp_userinfo():
    auth = request.headers.get('Authorization', '')
    info = _userinfo_for(auth[7:] if auth.startswith('Bearer ') else '')
    return jsonify(info), (401 if 'error' in info else 200)
