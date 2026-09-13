/* Level 2 — HTTP demos. One file, one section per page, picked by LAB_PAGE. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var page = window.LAB_PAGE;
        var wireNode = document.getElementById('wire');
        var wire = wireNode ? new Lab.WireLog(wireNode) : { add: function () {}, clear: function () {} };
        var pause = document.getElementById('pause'), clearLog = document.getElementById('clearLog');
        if (pause) pause.addEventListener('change', function (e) { wire.paused = e.target.checked; });
        if (clearLog) clearLog.addEventListener('click', function () { wire.clear(); });

        function tile(value, label, cls) {
            var t = Lab.el('div', 'stat-tile' + (cls ? ' ' + cls : ''));
            t.appendChild(Lab.el('div', 'stat-tile__value', value));
            t.appendChild(Lab.el('div', 'stat-tile__label', label));
            return t;
        }
        function setTiles(node, tiles) {
            while (node.firstChild) node.removeChild(node.firstChild);
            tiles.forEach(function (t) { node.appendChild(tile(t[0], t[1], t[2])); });
        }
        /* Resource Timing entry for the last fetch of a URL — the only way JS
           can see transfer sizes and whether the cache was used. */
        function timing(url) {
            var entries = performance.getEntriesByName(new URL(url, location.href).href);
            return entries.length ? entries[entries.length - 1] : null;
        }
        function headersText(r) {
            var out = [];
            r.headers.forEach(function (v, k) { out.push(k + ': ' + v); });
            return out.join('\n');
        }

        /* ================================================================ */
        if (page === 'caching') {
            var etag = null, stats = { requests: 0, full: 0, notModified: 0, fromCache: 0, bytes: 0 };
            var statsNode = document.getElementById('stats'), last = document.getElementById('last');

            function render() {
                setTiles(statsNode, [
                    [stats.requests, 'clicks'], [stats.full, '200 full body'], [stats.notModified, '304 no body', 'stat-tile--good'],
                    [stats.fromCache, 'served from cache', 'stat-tile--good'], [Lab.bytes(stats.bytes), 'body bytes downloaded']
                ]);
            }
            render();

            async function get(mode) {
                stats.requests += 1;
                var url = '/lab/api/http/resource?mode=' + mode;
                var init = { headers: {} };
                if (mode === 'etag') {
                    // Do the conditional request ourselves so the 304 is visible to JS.
                    init.cache = 'no-store';
                    if (etag) init.headers['If-None-Match'] = etag;
                    wire.add('out', 'GET ' + url + (etag ? '\nIf-None-Match: ' + etag : ''));
                } else if (mode === 'maxage') {
                    init.cache = 'default';                 // let the browser cache decide
                    wire.add('out', 'GET ' + url + '   (browser may answer from its cache)');
                } else {
                    init.cache = 'no-store';
                    wire.add('out', 'GET ' + url);
                }
                var t0 = performance.now();
                var r = await fetch(url, init);
                var ms = Math.round(performance.now() - t0);
                var text = r.status === 304 ? '' : await r.text();
                var entry = timing(url);
                var fromCache = entry && entry.transferSize === 0 && r.status === 200;

                if (r.status === 304) { stats.notModified += 1; }
                else if (fromCache) { stats.fromCache += 1; }
                else { stats.full += 1; stats.bytes += text.length; }
                if (r.headers.get('ETag')) etag = r.headers.get('ETag');

                wire.add(r.status === 304 ? 'sys' : 'in',
                    r.status + ' ' + r.statusText + (fromCache ? '  (from browser cache — no request was sent)' : '') +
                    '\n' + headersText(r).split('\n').filter(function (l) { return /^(etag|cache-control|content-length)/i.test(l); }).join('\n'),
                    (fromCache ? '0 B' : (text.length + ' B')) + ' · ' + ms + ' ms');
                last.textContent = 'HTTP ' + r.status + ' ' + r.statusText + '\n' + headersText(r) + '\n\n' + (text || '(empty body)');
                render();
            }
            document.querySelectorAll('[data-mode]').forEach(function (b) {
                b.addEventListener('click', function () { get(b.dataset.mode).catch(function (e) { wire.add('err', e.message); }); });
            });
            document.getElementById('bump').addEventListener('click', async function () {
                var r = await fetch('/lab/api/http/resource/bump', { method: 'POST' });
                var d = await r.json();
                wire.add('sys', 'document changed on the server → version ' + d.version + '. Next ETag check will miss.');
            });
        }

        /* ================================================================ */
        if (page === 'compression') {
            var rows = document.getElementById('rows'), bars = document.getElementById('bars');
            var results = {};

            async function run(encoding) {
                var url = '/lab/api/http/payload?encoding=' + encoding + '&t=' + Date.now();
                wire.add('out', 'GET ' + url.split('&')[0], 'Accept-Encoding forced: ' + encoding);
                var t0 = performance.now();
                var r = await fetch(url, { cache: 'no-store' });
                var json = await r.json();
                var ms = Math.round(performance.now() - t0);
                var entry = timing(url);
                var wireBytes = entry && entry.encodedBodySize ? entry.encodedBodySize : parseInt(r.headers.get('content-length') || '0', 10);
                var decoded = entry && entry.decodedBodySize ? entry.decodedBodySize : parseInt(r.headers.get('x-uncompressed-length') || '0', 10);
                results[encoding] = { wire: wireBytes, decoded: decoded, ms: ms, items: json.items.length };
                wire.add('in', '200  Content-Encoding: ' + (r.headers.get('content-encoding') || '(none)') + '  →  ' + json.items.length + ' items parsed normally',
                    Lab.bytes(wireBytes) + ' on the wire · ' + Lab.bytes(decoded) + ' decoded · ' + ms + ' ms');
                render();
            }
            function render() {
                while (rows.firstChild) rows.removeChild(rows.firstChild);
                while (bars.firstChild) bars.removeChild(bars.firstChild);
                var max = 0;
                Object.keys(results).forEach(function (k) { max = Math.max(max, results[k].wire); });
                ['identity', 'gzip', 'br'].forEach(function (k) {
                    var res = results[k]; if (!res) return;
                    var tr = Lab.el('tr');
                    tr.appendChild(Lab.el('td', 'key', k));
                    tr.appendChild(Lab.el('td', null, Lab.bytes(res.wire)));
                    tr.appendChild(Lab.el('td', null, Lab.bytes(res.decoded)));
                    var saved = res.decoded ? Math.round((1 - res.wire / res.decoded) * 100) : 0;
                    tr.appendChild(Lab.el('td', null, saved + '%'));
                    tr.appendChild(Lab.el('td', null, res.ms + ' ms'));
                    rows.appendChild(tr);
                    var row = Lab.el('div');
                    row.appendChild(Lab.el('div', 'small muted', k + ' — ' + Lab.bytes(res.wire)));
                    var bar = Lab.el('div', 'score-list__bar'); bar.style.height = '12px';
                    var fill = Lab.el('span'); fill.style.width = (max ? res.wire / max * 100 : 0) + '%';
                    if (k !== 'identity') fill.style.background = 'var(--accent)';
                    bar.appendChild(fill); row.appendChild(bar); bars.appendChild(row);
                });
            }
            document.querySelectorAll('[data-encoding]').forEach(function (b) {
                b.addEventListener('click', function () { run(b.dataset.encoding).catch(function (e) { wire.add('err', e.message); }); });
            });
            document.getElementById('runAll').addEventListener('click', async function () {
                for (var k of ['identity', 'gzip', 'br']) { try { await run(k); } catch (e) { wire.add('err', e.message); } }
            });
        }

        /* ================================================================ */
        if (page === 'range-requests') {
            var meta = null, parts = [], received = 0, controller = null, running = false;
            var bar = document.getElementById('bar'), progress = document.getElementById('progress'), recv = document.getElementById('received');
            var startB = document.getElementById('start'), pauseB = document.getElementById('pause'), resumeB = document.getElementById('resume'), resetB = document.getElementById('reset');
            var chunkIn = document.getElementById('chunk'), chunkOut = document.querySelector('output[for="chunk"]');
            var verify = document.getElementById('verify');
            chunkIn.addEventListener('input', function () { chunkOut.textContent = chunkIn.value + ' KB'; });

            fetch('/lab/api/http/blob/meta').then(function (r) { return r.json(); }).then(function (d) {
                meta = d; document.getElementById('meta').textContent = Lab.bytes(d.size) + ' file · server SHA-256 ' + d.sha256.slice(0, 16) + '…';
            });
            function paint() {
                var pct = meta ? received / meta.size * 100 : 0;
                bar.style.width = pct + '%'; progress.textContent = pct.toFixed(1) + '%'; recv.textContent = Lab.bytes(received) + ' received';
            }
            function buttons(state) {
                startB.disabled = state !== 'idle'; pauseB.disabled = state !== 'running'; resumeB.disabled = state !== 'paused';
            }
            async function loop() {
                running = true; buttons('running');
                var chunk = parseInt(chunkIn.value, 10) * 1024;
                while (running && received < meta.size) {
                    var end = Math.min(received + chunk, meta.size) - 1;
                    var range = 'bytes=' + received + '-' + end;
                    controller = new AbortController();
                    wire.add('out', 'GET /lab/api/http/blob\nRange: ' + range);
                    var t0 = performance.now();
                    try {
                        var r = await fetch('/lab/api/http/blob', { headers: { Range: range }, signal: controller.signal, cache: 'no-store' });
                        if (r.status !== 206) { wire.add('err', r.status + ' ' + r.statusText + ' — expected 206 Partial Content'); running = false; break; }
                        var buf = await r.arrayBuffer();
                        parts.push(buf); received += buf.byteLength;
                        wire.add('in', '206 Partial Content\nContent-Range: ' + r.headers.get('Content-Range'), Lab.bytes(buf.byteLength) + ' · ' + Math.round(performance.now() - t0) + ' ms');
                        paint();
                    } catch (e) {
                        if (e.name === 'AbortError') { wire.add('sys', 'paused — the in-flight chunk was abandoned; the next request resumes from byte ' + received); }
                        else { wire.add('err', e.message); running = false; }
                        break;
                    }
                }
                if (received >= (meta ? meta.size : Infinity)) { buttons('done'); await check(); }
                else buttons(running ? 'running' : 'paused');
            }
            async function check() {
                var total = new Uint8Array(received), off = 0;
                parts.forEach(function (p) { total.set(new Uint8Array(p), off); off += p.byteLength; });
                var digest = await crypto.subtle.digest('SHA-256', total);
                var hex = Array.from(new Uint8Array(digest)).map(function (b) { return b.toString(16).padStart(2, '0'); }).join('');
                while (verify.firstChild) verify.removeChild(verify.firstChild);
                var ok = hex === meta.sha256;
                verify.appendChild(UI ? UI.alert(ok ? 'success' : 'error', ok ? 'Intact: browser hash matches the server after ' + parts.length + ' partial requests.' : 'MISMATCH — the file was corrupted in reassembly.') : Lab.el('p', null, ok ? 'ok' : 'bad'));
                verify.appendChild(Lab.el('pre', 'small', 'server  ' + meta.sha256 + '\nbrowser ' + hex));
                wire.add(ok ? 'sys' : 'err', 'SHA-256 ' + (ok ? 'verified' : 'MISMATCH'));
            }
            startB.addEventListener('click', function () { if (meta) loop(); });
            pauseB.addEventListener('click', function () { running = false; if (controller) controller.abort(); });
            resumeB.addEventListener('click', function () { loop(); });
            resetB.addEventListener('click', function () {
                running = false; if (controller) controller.abort();
                parts = []; received = 0; paint(); buttons('idle'); wire.clear();
                while (verify.firstChild) verify.removeChild(verify.firstChild);
            });
            paint(); buttons('idle');
        }

        /* ================================================================ */
        if (page === 'streaming') {
            var stats = {}, statsNode = document.getElementById('stats');
            function render() {
                setTiles(statsNode, [
                    [stats.bufFirst === undefined ? '—' : stats.bufFirst + ' ms', 'buffered: first byte', 'stat-tile--bad'],
                    [stats.strFirst === undefined ? '—' : stats.strFirst + ' ms', 'streamed: first byte', 'stat-tile--good'],
                    [stats.bufTotal === undefined ? '—' : stats.bufTotal + ' ms', 'buffered: total'],
                    [stats.strTotal === undefined ? '—' : stats.strTotal + ' ms', 'streamed: total']
                ]);
            }
            render();
            async function run(mode) {
                var out = document.getElementById(mode === 'buffered' ? 'bufOut' : 'strOut');
                var state = document.getElementById(mode === 'buffered' ? 'bufState' : 'strState');
                while (out.firstChild) out.removeChild(out.firstChild);
                state.textContent = 'waiting…';
                wire.add('out', 'GET /lab/api/http/lines?mode=' + mode);
                var t0 = performance.now(), first = null, count = 0;
                var r = await fetch('/lab/api/http/lines?mode=' + mode, { cache: 'no-store' });
                var reader = r.body.getReader(), decoder = new TextDecoder(), buffer = '';
                while (true) {
                    var chunk = await reader.read();
                    if (chunk.done) break;
                    if (first === null) { first = Math.round(performance.now() - t0); wire.add('in', mode + ': first bytes arrived', first + ' ms'); }
                    buffer += decoder.decode(chunk.value, { stream: true });
                    var lines = buffer.split('\n'); buffer = lines.pop();
                    lines.forEach(function (line) {
                        if (!line.trim()) return;
                        var d = JSON.parse(line); count += 1;
                        var l = Lab.el('div', 'wire__line');
                        l.appendChild(Lab.el('span', 'wire__time', Math.round(performance.now() - t0) + ' ms'));
                        l.appendChild(Lab.el('span', 'wire__dir in', '←'));
                        l.appendChild(Lab.el('span', 'wire__text', d.step + '/' + d.of + ' ' + d.message));
                        l.appendChild(Lab.el('span', 'wire__meta', ''));
                        out.appendChild(l); out.scrollTop = out.scrollHeight;
                        state.textContent = count + ' of ' + d.of;
                    });
                }
                var total = Math.round(performance.now() - t0);
                if (mode === 'buffered') { stats.bufFirst = first; stats.bufTotal = total; } else { stats.strFirst = first; stats.strTotal = total; }
                state.textContent = 'done in ' + total + ' ms';
                wire.add('in', mode + ': complete, ' + count + ' records', total + ' ms');
                render();
            }
            document.getElementById('buffered').addEventListener('click', function () { run('buffered'); });
            document.getElementById('streamed').addEventListener('click', function () { run('streamed'); });
            document.getElementById('both').addEventListener('click', function () { run('buffered'); run('streamed'); });
        }

        /* ================================================================ */
        if (page === 'cors') {
            // Same server, different origin: localhost <-> 127.0.0.1.
            var here = location.hostname;
            var other = here === 'localhost' ? '127.0.0.1' : 'localhost';
            var target = location.protocol + '//' + other + (location.port ? ':' + location.port : '');
            var note = document.getElementById('originNote');
            note.textContent = 'This page is ' + location.origin + '. It will call ' + target + ' — the same Flask process, but a different origin to the browser, so CORS rules apply.';
            var outcome = document.getElementById('outcome'), hitsNode = document.getElementById('hits'), policy = document.getElementById('policy');

            async function refreshHits() {
                var r = await fetch('/lab/api/http/cors/hits'); var d = await r.json();
                setTiles(hitsNode, [[d.requests, 'real requests reached server'], [d.preflights, 'preflights (OPTIONS)']]);
            }
            document.getElementById('resetHits').addEventListener('click', async function () { await fetch('/lab/api/http/cors/reset', { method: 'POST' }); refreshHits(); wire.clear(); });
            fetch('/lab/api/http/cors/reset', { method: 'POST' }).then(refreshHits);      // also sets the demo cookie

            var REQUESTS = {
                simple: function (url) { return { url: url, init: {} , label: 'simple GET (no preflight)' }; },
                custom: function (url) { return { url: url, init: { headers: { 'X-Demo': '1' } }, label: 'GET with X-Demo → preflight required' }; },
                json:   function (url) { return { url: url, init: { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"hello":1}' }, label: 'POST application/json → preflight required' }; },
                creds:  function (url) { return { url: url, init: { credentials: 'include' }, label: 'GET with credentials: include → needs Allow-Credentials and a non-* origin' }; }
            };
            document.querySelectorAll('[data-req]').forEach(function (b) {
                b.addEventListener('click', async function () {
                    var p = policy.value;
                    var req = REQUESTS[b.dataset.req](target + '/lab/api/http/cors?policy=' + p);
                    wire.add('out', (req.init.method || 'GET') + ' ' + req.url + '\n' + req.label + (req.init.headers ? '\n' + Object.keys(req.init.headers).map(function (k) { return k + ': ' + req.init.headers[k]; }).join('\n') : ''));
                    while (outcome.firstChild) outcome.removeChild(outcome.firstChild);
                    try {
                        var r = await fetch(req.url, Object.assign({ cache: 'no-store' }, req.init));
                        var d = await r.json();
                        wire.add('in', r.status + ' — readable. Exposed headers:\n' + headersText(r), '');
                        outcome.appendChild(UI.alert('success', 'Allowed. The browser let your code read the response.'));
                        outcome.appendChild(Lab.el('pre', 'small', JSON.stringify(d, null, 2)));
                    } catch (e) {
                        wire.add('err', 'fetch() rejected: ' + e.message + '\nThe browser refused to hand the response to JavaScript. Open DevTools → Console for the exact CORS reason.');
                        outcome.appendChild(UI.alert('error', 'Blocked by the browser: ' + e.message));
                        var why = { none: 'No Access-Control-Allow-Origin header came back, so the response is opaque to you.',
                                    wildcard: b.dataset.req === 'creds' ? '"*" is not allowed together with credentials — the origin must be spelled out.' : (b.dataset.req !== 'simple' ? 'The preflight got no Allow-Headers / Allow-Methods, so the real request was never sent.' : 'Unexpected — check the console.'),
                                    origin: b.dataset.req === 'simple' ? 'Unexpected — check the console.' : (b.dataset.req === 'creds' ? 'Allow-Origin is right but Allow-Credentials is missing.' : 'The preflight got no Allow-Headers / Allow-Methods, so the real request was never sent.'),
                                    preflight: b.dataset.req === 'creds' ? 'Everything but Allow-Credentials: true.' : 'Unexpected — check the console.',
                                    credentials: 'Unexpected — check the console.' }[p];
                        outcome.appendChild(Lab.el('p', 'small muted', why));
                    }
                    setTimeout(refreshHits, 150);
                });
            });
        }
    });
})();
