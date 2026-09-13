"""Level 0 — fundamentals: what a request is, the methods, the status codes, headers, encodings.

    *    /lab/api/basics/echo                 returns exactly what the server received
    *    /lab/api/basics/notes[/<id>]         a tiny REST resource: GET POST PUT PATCH DELETE HEAD OPTIONS
    GET  /lab/api/basics/status/<code>        respond with that status, with the right companion headers
    GET  /lab/api/basics/negotiate            same data as JSON / HTML / text / CSV, chosen by Accept
    POST /lab/api/basics/decode               parse a body however it was encoded, and say how
"""
import json
import threading
import time

from flask import Response, jsonify, make_response, redirect, request, url_for

from app.blueprints.lab import bp

_lock = threading.Lock()
_notes: dict[int, dict] = {1: {'id': 1, 'title': 'Buy milk', 'done': False}, 2: {'id': 2, 'title': 'Read RFC 9110', 'done': True}}
_next_id = 3


def _request_view() -> dict:
    """Everything the server can see about the current request, for the echo pages."""
    body = request.get_data()
    try:
        body_text = body.decode('utf-8')
    except UnicodeDecodeError:
        body_text = f'<{len(body)} binary bytes>'
    return {
        'method': request.method,
        'path': request.path,
        'query_string': request.query_string.decode(),
        'query': {k: request.args.getlist(k) if len(request.args.getlist(k)) > 1 else v for k, v in request.args.items()},
        'http_version': request.environ.get('SERVER_PROTOCOL'),
        'headers': [[k, v] for k, v in request.headers.items()],
        'cookies': dict(request.cookies),
        'content_type': request.content_type,
        'content_length': request.content_length,
        'body': body_text if len(body_text) <= 2000 else body_text[:2000] + '…',
        'form': {k: request.form.getlist(k) if len(request.form.getlist(k)) > 1 else v for k, v in request.form.items()} if request.form else None,
        'json': request.get_json(silent=True),
        'files': [{'field': k, 'filename': f.filename, 'content_type': f.content_type, 'bytes': len(f.read())} for k, f in request.files.items()],
        'remote_addr': request.remote_addr,
        'received_at': time.strftime('%H:%M:%S'),
    }


def _raw_request_text(view: dict) -> str:
    lines = [f"{view['method']} {view['path']}{'?' + view['query_string'] if view['query_string'] else ''} {view['http_version']}"]
    lines += [f'{k}: {v}' for k, v in view['headers']]
    lines.append('')
    lines.append(view['body'] if view['body'] else '')
    return '\n'.join(lines).rstrip('\n')


# ---------------------------------------------------------------------------
# 1. Anatomy: echo
# ---------------------------------------------------------------------------

@bp.route('/api/basics/echo', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'], endpoint='api_basics_echo')
def echo():
    view = _request_view()
    payload = {'ok': True, 'request': view, 'raw': _raw_request_text(view)}
    response = jsonify(payload)
    response.headers['X-Echoed-Method'] = request.method
    response.headers['Cache-Control'] = 'no-store'
    if request.method == 'OPTIONS':
        response.headers['Allow'] = 'GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS'
    return response


# ---------------------------------------------------------------------------
# 2. Methods: a tiny REST resource
# ---------------------------------------------------------------------------

ALLOW_COLLECTION = 'GET, POST, HEAD, OPTIONS'
ALLOW_ITEM = 'GET, PUT, PATCH, DELETE, HEAD, OPTIONS'


@bp.route('/api/basics/notes', methods=['GET', 'POST', 'HEAD', 'OPTIONS'], endpoint='api_basics_notes')
def notes_collection():
    global _next_id
    if request.method == 'OPTIONS':
        response = make_response('', 204)
        response.headers['Allow'] = ALLOW_COLLECTION
        return response
    if request.method in ('GET', 'HEAD'):
        with _lock:
            items = sorted(_notes.values(), key=lambda n: n['id'])
        response = jsonify({'ok': True, 'notes': items, 'count': len(items)})
        response.headers['X-Total-Count'] = str(len(items))
        return response                                  # Flask strips the body for HEAD itself
    # POST: create
    data = request.get_json(silent=True) or {}
    title = str(data.get('title', '')).strip()
    if not title:
        return jsonify({'ok': False, 'error': 'title is required'}), 422
    with _lock:
        note = {'id': _next_id, 'title': title[:120], 'done': bool(data.get('done', False))}
        _notes[_next_id] = note
        _next_id += 1
    response = jsonify({'ok': True, 'note': note})
    response.status_code = 201
    response.headers['Location'] = url_for('lab.api_basics_note', note_id=note['id'])
    return response


@bp.route('/api/basics/notes/<int:note_id>', methods=['GET', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'], endpoint='api_basics_note')
def note_item(note_id):
    if request.method == 'OPTIONS':
        response = make_response('', 204)
        response.headers['Allow'] = ALLOW_ITEM
        return response
    with _lock:
        note = _notes.get(note_id)
        if note is None:
            return jsonify({'ok': False, 'error': f'note {note_id} does not exist'}), 404
        if request.method in ('GET', 'HEAD'):
            return jsonify({'ok': True, 'note': note})
        if request.method == 'DELETE':
            del _notes[note_id]
            return '', 204
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({'ok': False, 'error': 'send a JSON body with Content-Type: application/json'}), 415
        if request.method == 'PUT':
            # Replace: every field must be present; anything omitted is gone.
            if 'title' not in data or 'done' not in data:
                return jsonify({'ok': False, 'error': 'PUT replaces the whole resource — send both title and done'}), 422
            _notes[note_id] = {'id': note_id, 'title': str(data['title'])[:120], 'done': bool(data['done'])}
        else:
            # PATCH: change only what was sent.
            if 'title' in data:
                note['title'] = str(data['title'])[:120]
            if 'done' in data:
                note['done'] = bool(data['done'])
        return jsonify({'ok': True, 'note': _notes[note_id]})


@bp.post('/api/basics/notes/reset', endpoint='api_basics_notes_reset')
def notes_reset():
    global _next_id
    with _lock:
        _notes.clear()
        _notes.update({1: {'id': 1, 'title': 'Buy milk', 'done': False}, 2: {'id': 2, 'title': 'Read RFC 9110', 'done': True}})
        _next_id = 3
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# 3. Status codes
# ---------------------------------------------------------------------------

STATUS_INFO = {
    200: ('OK', 'The request worked; here is the result.'),
    201: ('Created', 'A new resource exists; Location says where.'),
    202: ('Accepted', 'Taken on, not done yet (see Level 3, background jobs).'),
    204: ('No Content', 'Worked, nothing to return. Typical for DELETE.'),
    301: ('Moved Permanently', 'Use the new URL from now on. Browsers and caches remember it.'),
    302: ('Found', 'Go here for now; keep using the old URL next time.'),
    304: ('Not Modified', 'Your cached copy is still good (see Level 2, caching).'),
    307: ('Temporary Redirect', 'Like 302 but the method must not change: a POST stays a POST.'),
    308: ('Permanent Redirect', 'Like 301 but the method must not change.'),
    400: ('Bad Request', 'The request itself is malformed — the server could not even parse it.'),
    401: ('Unauthorized', 'Really means "unauthenticated": who are you? WWW-Authenticate says how to answer.'),
    403: ('Forbidden', 'The server knows who you are and the answer is no.'),
    404: ('Not Found', 'Nothing lives at this URL. Also used to hide things that exist.'),
    405: ('Method Not Allowed', 'The URL exists but not for this verb. Allow lists the ones that work.'),
    409: ('Conflict', 'The request clashes with the current state (see Level 6, locking).'),
    410: ('Gone', 'It existed, it was removed on purpose, it is not coming back.'),
    413: ('Content Too Large', 'The body exceeds what the server accepts.'),
    415: ('Unsupported Media Type', 'The Content-Type you sent is not one the server reads.'),
    418: ("I'm a teapot", 'An April Fools RFC from 1998 that every framework still implements.'),
    422: ('Unprocessable Content', 'Well-formed but semantically wrong: validation failed.'),
    429: ('Too Many Requests', 'Slow down; Retry-After says how long (see Level 3, rate limiting).'),
    500: ('Internal Server Error', 'The server crashed while handling this. Never the client\'s fault.'),
    501: ('Not Implemented', 'The server does not support this method at all.'),
    502: ('Bad Gateway', 'A proxy in front got a bad answer from the real server.'),
    503: ('Service Unavailable', 'Overloaded or down for maintenance; usually temporary. Retry-After may help.'),
    504: ('Gateway Timeout', 'A proxy waited for the real server and gave up.'),
}


@bp.get('/api/basics/status/<int:code>', endpoint='api_basics_status')
def status(code):
    if code not in STATUS_INFO:
        return jsonify({'ok': False, 'error': f'{code} is not in this demo'}), 400
    reason, meaning = STATUS_INFO[code]

    if code in (301, 302, 307, 308):
        response = redirect(url_for('lab.api_basics_status', code=200, via=code), code=code)
        response.headers['X-Explain'] = meaning
        return response
    if code == 304:
        response = make_response('', 304)
        response.headers['ETag'] = '"demo-etag"'
        return response
    if code == 204:
        response = make_response('', 204)
        response.headers['X-Explain'] = meaning
        return response

    body = {'ok': code < 400, 'status': code, 'reason': reason, 'meaning': meaning}
    if request.args.get('via'):
        body['note'] = f"you were redirected here by a {request.args['via']}; fetch() followed it for you — check response.redirected"
    response = jsonify(body)
    response.status_code = code
    if code == 201:
        response.headers['Location'] = '/lab/api/basics/notes/42'
    if code == 401:
        response.headers['WWW-Authenticate'] = 'Bearer realm="web-lab"'
    if code == 405:
        response.headers['Allow'] = 'GET, HEAD'
    if code in (429, 503):
        response.headers['Retry-After'] = '5'
    if code == 413:
        response.headers['X-Max-Bytes'] = '1048576'
    return response


@bp.get('/api/basics/status', endpoint='api_basics_status_list')
def status_list():
    return jsonify({'ok': True, 'codes': [{'code': c, 'reason': r, 'meaning': m} for c, (r, m) in sorted(STATUS_INFO.items())]})


# ---------------------------------------------------------------------------
# 4. Headers & content negotiation
# ---------------------------------------------------------------------------

_PEOPLE = [{'name': 'Ada Lovelace', 'born': 1815, 'field': 'mathematics'},
           {'name': 'Grace Hopper', 'born': 1906, 'field': 'compilers'},
           {'name': 'Alan Turing', 'born': 1912, 'field': 'computability'}]


@bp.get('/api/basics/negotiate', endpoint='api_basics_negotiate')
def negotiate():
    # Real negotiation: pick the best type the client says it accepts.
    best = request.accept_mimetypes.best_match(['application/json', 'text/html', 'text/csv', 'text/plain']) or 'application/json'
    lang = request.accept_languages.best_match(['en', 'fil', 'es']) or 'en'
    greeting = {'en': 'Pioneers', 'fil': 'Mga tagapanguna', 'es': 'Pioneras y pioneros'}[lang]

    if best == 'text/html':
        rows = ''.join(f"<tr><td>{p['name']}</td><td>{p['born']}</td><td>{p['field']}</td></tr>" for p in _PEOPLE)
        body = f'<h2>{greeting}</h2><table border="1" cellpadding="4"><tr><th>name</th><th>born</th><th>field</th></tr>{rows}</table>'
    elif best == 'text/csv':
        body = 'name,born,field\n' + '\n'.join(f"{p['name']},{p['born']},{p['field']}" for p in _PEOPLE) + '\n'
    elif best == 'text/plain':
        body = f'{greeting}\n' + '\n'.join(f"- {p['name']} ({p['born']}), {p['field']}" for p in _PEOPLE) + '\n'
    else:
        body = json.dumps({'title': greeting, 'people': _PEOPLE}, indent=2, ensure_ascii=False)

    response = Response(body, mimetype=best)
    response.headers['Content-Language'] = lang
    response.headers['Vary'] = 'Accept, Accept-Language'
    response.headers['X-Chosen-Because'] = f"Accept: {request.headers.get('Accept', '(none)')[:80]}"
    response.headers['Cache-Control'] = 'no-store'
    return response


# ---------------------------------------------------------------------------
# 5. Sending data: how the body was encoded and how the server read it
# ---------------------------------------------------------------------------

@bp.post('/api/basics/decode', endpoint='api_basics_decode')
def decode():
    view = _request_view()
    ctype = (request.content_type or '').split(';')[0]
    if ctype == 'application/json':
        how = 'json.loads(body) — one parse, nested structures and real types survive (numbers stay numbers, lists stay lists).'
        parsed = request.get_json(silent=True)
    elif ctype == 'application/x-www-form-urlencoded':
        how = 'urlencoded key=value pairs joined by &. Everything is a string; repeated keys become a list. What a plain <form> sends.'
        parsed = view['form']
    elif ctype == 'multipart/form-data':
        how = 'each field is its own part with headers, separated by the boundary. The only way to send files alongside fields.'
        parsed = {'fields': view['form'], 'files': view['files']}
    elif ctype == 'text/plain':
        how = 'raw text; the server reads request.get_data() and decides what it means.'
        parsed = view['body']
    else:
        how = f'unknown or missing Content-Type ({ctype or "none"}); the server has to guess, and mostly refuses.'
        parsed = None
    return jsonify({'ok': True, 'content_type': request.content_type, 'content_length': request.content_length,
                    'how_the_server_read_it': how, 'parsed': parsed, 'query': view['query'], 'raw_body': view['body']})
