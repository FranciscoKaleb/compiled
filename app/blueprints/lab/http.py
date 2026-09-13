"""Level 2 — HTTP itself: caching, compression, range requests, streaming, CORS.

    GET  /lab/api/http/resource?mode=none|etag|maxage    a small JSON document with different cache policies
    POST /lab/api/http/resource/bump                      change it, so ETags stop matching
    GET  /lab/api/http/payload?encoding=identity|gzip|br  ~60 KB of JSON, compressed as asked
    GET  /lab/api/http/blob                               5 MB deterministic file, supports Range
    GET  /lab/api/http/blob/meta                          its size and SHA-256
    GET  /lab/api/http/lines?mode=buffered|streamed       20 lines over ~4 s, all at once or as they happen
    *    /lab/api/http/cors?policy=...                    cross-origin target with switchable headers
    GET  /lab/api/http/cors/hits                          how many requests actually reached the server
"""
import gzip
import hashlib
import io
import json
import random
import threading
import time
import zlib

from flask import Response, jsonify, make_response, request, send_file, stream_with_context

from app.blueprints.lab import bp

# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

_resource_lock = threading.Lock()
_resource_version = 1


def _resource() -> tuple[dict, str]:
    with _resource_lock:
        version = _resource_version
    body = {
        'id': 42, 'name': 'Ada Lovelace', 'title': 'Analyst, Metaphysician, Founder of Scientific Computing',
        'version': version, 'tags': ['mathematics', 'engines', 'notes'],
        'bio': 'Wrote what is regarded as the first algorithm intended for a machine. ' * 3,
    }
    etag = '"' + hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16] + '"'
    return body, etag


@bp.get('/api/http/resource', endpoint='api_http_resource')
def resource():
    mode = request.args.get('mode', 'none')
    body, etag = _resource()
    time.sleep(0.15)                       # a little "database" latency, so hits are visible

    if mode == 'etag':
        # Conditional request: identical resource -> 304, no body.
        if request.headers.get('If-None-Match') == etag:
            response = make_response('', 304)
            response.headers['ETag'] = etag
            response.headers['Cache-Control'] = 'no-cache'     # "always revalidate", not "never cache"
            return response
        response = jsonify(body)
        response.headers['ETag'] = etag
        response.headers['Cache-Control'] = 'no-cache'
        return response

    if mode == 'maxage':
        response = jsonify(body)
        response.headers['Cache-Control'] = 'public, max-age=10'
        response.headers['ETag'] = etag
        return response

    response = jsonify(body)
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.post('/api/http/resource/bump', endpoint='api_http_resource_bump')
def resource_bump():
    global _resource_version
    with _resource_lock:
        _resource_version += 1
        version = _resource_version
    return jsonify({'ok': True, 'version': version})


# ---------------------------------------------------------------------------
# Compression
# ---------------------------------------------------------------------------

def _payload() -> bytes:
    rng = random.Random(7)
    rows = [{
        'id': i, 'sku': f'SKU-{i:05d}', 'name': rng.choice(['Widget', 'Gadget', 'Doohickey', 'Gizmo']) + f' {i}',
        'price': round(rng.uniform(1, 500), 2), 'in_stock': rng.random() > 0.3,
        'tags': rng.sample(['red', 'blue', 'green', 'large', 'small', 'metal', 'wood', 'sale'], 3),
        'description': 'A very ordinary product description that repeats across many rows.',
    } for i in range(600)]
    return json.dumps({'items': rows}, indent=2).encode()


_PAYLOAD = _payload()


@bp.get('/api/http/payload', endpoint='api_http_payload')
def payload():
    encoding = request.args.get('encoding', 'identity')
    data = _PAYLOAD
    if encoding == 'gzip':
        data = gzip.compress(_PAYLOAD, compresslevel=6)
    elif encoding == 'deflate':
        data = zlib.compress(_PAYLOAD, 6)
    elif encoding == 'br':
        try:
            import brotli
            data = brotli.compress(_PAYLOAD, quality=5)
        except ImportError:
            return jsonify({'ok': False, 'error': 'brotli is not installed on the server'}), 501
    else:
        encoding = 'identity'

    response = Response(data, mimetype='application/json')
    if encoding != 'identity':
        response.headers['Content-Encoding'] = encoding
    response.headers['Content-Length'] = str(len(data))
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Uncompressed-Length'] = str(len(_PAYLOAD))
    # Different encodings of the same URL must not be conflated by caches.
    response.headers['Vary'] = 'Accept-Encoding'
    return response


# ---------------------------------------------------------------------------
# Range requests
# ---------------------------------------------------------------------------

def _blob() -> bytes:
    # 5 MB, deterministic, incompressible enough to feel like a real download.
    rng = random.Random(2024)
    return bytes(rng.getrandbits(8) for _ in range(5 * 1024 * 1024))


_BLOB = _blob()
_BLOB_SHA = hashlib.sha256(_BLOB).hexdigest()


@bp.get('/api/http/blob/meta', endpoint='api_http_blob_meta')
def blob_meta():
    return jsonify({'ok': True, 'size': len(_BLOB), 'sha256': _BLOB_SHA})


@bp.get('/api/http/blob', endpoint='api_http_blob')
def blob():
    # Throttled a little so a 5 MB download takes a few seconds and can be paused.
    range_header = request.headers.get('Range')
    start, end = 0, len(_BLOB) - 1
    status = 200
    if range_header and range_header.startswith('bytes='):
        try:
            first, _, last = range_header[6:].partition('-')
            start = int(first) if first else 0
            end = int(last) if last else len(_BLOB) - 1
            end = min(end, len(_BLOB) - 1)
            if start > end or start >= len(_BLOB):
                response = Response(status=416)
                response.headers['Content-Range'] = f'bytes */{len(_BLOB)}'
                return response
            status = 206
        except ValueError:
            pass

    chunk = _BLOB[start:end + 1]

    def generate():
        step = 64 * 1024
        for offset in range(0, len(chunk), step):
            yield chunk[offset:offset + step]
            time.sleep(0.02)                  # ~3 MB/s

    response = Response(stream_with_context(generate()), status=status, mimetype='application/octet-stream')
    response.headers['Accept-Ranges'] = 'bytes'
    response.headers['Content-Length'] = str(len(chunk))
    response.headers['Cache-Control'] = 'no-store'
    response.headers['ETag'] = f'"{_BLOB_SHA[:16]}"'
    if status == 206:
        response.headers['Content-Range'] = f'bytes {start}-{end}/{len(_BLOB)}'
    return response


# ---------------------------------------------------------------------------
# Streaming vs buffered
# ---------------------------------------------------------------------------

LINES = 20
LINE_DELAY = 0.2


def _work(i: int) -> str:
    return json.dumps({'step': i + 1, 'of': LINES, 'message': f'processed batch {i + 1}', 'at_ms': int(time.time() * 1000)})


@bp.get('/api/http/lines', endpoint='api_http_lines')
def lines():
    mode = request.args.get('mode', 'buffered')
    if mode == 'streamed':
        def generate():
            for i in range(LINES):
                time.sleep(LINE_DELAY)
                yield _work(i) + '\n'          # newline-delimited JSON: one record per line
        response = Response(stream_with_context(generate()), mimetype='application/x-ndjson')
        response.headers['X-Accel-Buffering'] = 'no'
        response.headers['Cache-Control'] = 'no-store'
        return response

    out = []
    for i in range(LINES):
        time.sleep(LINE_DELAY)
        out.append(_work(i))
    response = Response('\n'.join(out) + '\n', mimetype='application/x-ndjson')
    response.headers['Cache-Control'] = 'no-store'
    return response


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

_hits_lock = threading.Lock()
_hits = {'requests': 0, 'preflights': 0}


def _count(kind: str) -> None:
    with _hits_lock:
        _hits[kind] += 1


@bp.route('/api/http/cors', methods=['GET', 'POST', 'OPTIONS'], endpoint='api_http_cors')
def cors():
    """The target. `policy` decides which CORS headers come back.

    none        - no CORS headers at all: the browser blocks the response
    origin      - Access-Control-Allow-Origin echoes the caller's origin
    wildcard    - Access-Control-Allow-Origin: *
    preflight   - like `origin`, plus Allow-Headers/Methods so custom headers pass
    credentials - like `preflight`, plus Allow-Credentials for cookies
    """
    policy = request.args.get('policy', 'none')
    origin = request.headers.get('Origin', '')
    is_preflight = request.method == 'OPTIONS'
    _count('preflights' if is_preflight else 'requests')

    if is_preflight:
        response = make_response('', 204)
    else:
        response = jsonify({
            'ok': True,
            'message': 'the server answered happily',
            'saw_origin': origin or '(no Origin header — same-origin or not a browser)',
            'saw_custom_header': request.headers.get('X-Demo'),
            'cookie_seen': bool(request.cookies.get('lab_cors')),
            'method': request.method,
        })

    if policy in ('origin', 'preflight', 'credentials') and origin:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Vary'] = 'Origin'
    elif policy == 'wildcard':
        response.headers['Access-Control-Allow-Origin'] = '*'

    if policy in ('preflight', 'credentials'):
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Demo'
        response.headers['Access-Control-Max-Age'] = '5'      # short, so preflights stay visible
    if policy == 'credentials':
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.get('/api/http/cors/hits', endpoint='api_http_cors_hits')
def cors_hits():
    with _hits_lock:
        snapshot = dict(_hits)
    return jsonify({'ok': True, **snapshot})


@bp.post('/api/http/cors/reset', endpoint='api_http_cors_reset')
def cors_reset():
    with _hits_lock:
        _hits['requests'] = 0
        _hits['preflights'] = 0
    response = jsonify({'ok': True})
    response.set_cookie('lab_cors', 'yes', samesite='Lax', max_age=3600)
    return response
