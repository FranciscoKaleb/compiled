/* Level 0 — fundamentals. One section per page, picked by LAB_PAGE. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var page = window.LAB_PAGE;
        var wireNode = document.getElementById('wire');
        var wire = wireNode ? new Lab.WireLog(wireNode) : null;
        var pause = document.getElementById('pause'), clearLog = document.getElementById('clearLog');
        if (pause && wire) pause.addEventListener('change', function (e) { wire.paused = e.target.checked; });
        if (clearLog && wire) clearLog.addEventListener('click', function () { wire.clear(); });
        function clear(n) { while (n && n.firstChild) n.removeChild(n.firstChild); }
        function headersText(r) { var out = []; r.headers.forEach(function (v, k) { out.push(k + ': ' + v); }); return out.join('\n'); }
        function rawResponse(r, body) { return 'HTTP ' + r.status + ' ' + r.statusText + (r.redirected ? '   (redirected → ' + r.url + ')' : '') + '\n' + headersText(r) + '\n\n' + (body || '(empty body)'); }

        /* ================================================================ */
        if (page === 'anatomy') {
            function urlParts() {
                var q = document.getElementById('query').value.replace(/^\?/, ''), f = document.getElementById('fragment').value.replace(/^#/, '');
                var u = new URL('/lab/api/basics/echo' + (q ? '?' + q : '') + (f ? '#' + f : ''), location.href);
                var params = []; u.searchParams.forEach(function (v, k) { params.push(k + ' = ' + JSON.stringify(v)); });
                document.getElementById('urlParts').textContent =
                    u.href + '\n\n' +
                    'scheme    ' + u.protocol.replace(':', '') + '\n' +
                    'host      ' + u.hostname + '\n' +
                    'port      ' + (u.port || '(default)') + '\n' +
                    'path      ' + u.pathname + '\n' +
                    'query     ' + (u.search || '(none)') + (params.length ? '\n          ' + params.join('\n          ') : '') + '\n' +
                    'fragment  ' + (u.hash || '(none)') + '   ← stays in the browser';
                return u;
            }
            ['query', 'fragment'].forEach(function (id) { document.getElementById(id).addEventListener('input', urlParts); });
            urlParts();
            document.getElementById('send').addEventListener('click', async function () {
                var u = urlParts(), method = document.getElementById('method').value;
                var init = { method: method, headers: {}, cache: 'no-store' };
                var hdr = document.getElementById('hdr').value; var i = hdr.indexOf(':');
                if (i > 0) init.headers[hdr.slice(0, i).trim()] = hdr.slice(i + 1).trim();
                if (['POST', 'PUT', 'PATCH'].indexOf(method) !== -1) { init.body = document.getElementById('body').value; init.headers['Content-Type'] = 'application/json'; }
                var t0 = performance.now();
                var r = await fetch(u.href, init);
                var text = await r.text(); var ms = Math.round(performance.now() - t0);
                var data = null; try { data = JSON.parse(text); } catch (e) {}
                document.getElementById('rawReq').textContent = data ? data.raw : '(HEAD: no body came back, so the echo is empty — that is the point of HEAD)';
                document.getElementById('reqMeta').textContent = data ? data.request.headers.length + ' headers · body ' + (data.request.content_length || 0) + ' B' : '';
                document.getElementById('rawRes').textContent = rawResponse(r, text.length > 1500 ? text.slice(0, 1500) + '\n…' : text);
                document.getElementById('resMeta').textContent = ms + ' ms · ' + text.length + ' B body';
            });
        }

        /* ================================================================ */
        if (page === 'methods') {
            var base = '/lab/api/basics/notes';
            async function call(method, url, body) {
                var init = { method: method, cache: 'no-store', headers: {} };
                if (body !== undefined) { init.body = JSON.stringify(body); init.headers['Content-Type'] = 'application/json'; }
                wire.add('out', method + ' ' + url + (body !== undefined ? '\n' + JSON.stringify(body) : ''));
                var r = await fetch(url, init); var text = await r.text();
                var interesting = ['location', 'allow', 'x-total-count', 'content-length'].filter(function (h) { return r.headers.get(h) !== null; }).map(function (h) { return h + ': ' + r.headers.get(h); }).join('   ');
                wire.add(r.ok ? 'in' : 'err', r.status + ' ' + r.statusText + (interesting ? '\n' + interesting : '') + (text ? '\n' + text.slice(0, 300) : '\n(no body)'));
                return { r: r, text: text };
            }
            async function refresh() {
                var r = await fetch(base, { cache: 'no-store' }); var d = await r.json();
                var body = document.getElementById('notes'); clear(body);
                d.notes.forEach(function (n) { var tr = Lab.el('tr'); tr.appendChild(Lab.el('td', 'key', n.id)); tr.appendChild(Lab.el('td', null, n.title)); tr.appendChild(Lab.el('td', null, n.done ? '✓' : '—')); body.appendChild(tr); });
                document.getElementById('count').textContent = d.count + ' notes';
            }
            refresh();
            var OPS = {
                list: function () { return call('GET', base); },
                create: function () { return call('POST', base, { title: document.getElementById('title').value, done: document.getElementById('done').checked }); },
                get: function () { return call('GET', base + '/' + document.getElementById('noteId').value); },
                put: function () { return call('PUT', base + '/' + document.getElementById('noteId').value, { title: document.getElementById('title').value, done: document.getElementById('done').checked }); },
                patch: function () { return call('PATCH', base + '/' + document.getElementById('noteId').value, { done: document.getElementById('done').checked }); },
                delete: function () { return call('DELETE', base + '/' + document.getElementById('noteId').value); },
                head: function () { return call('HEAD', base); },
                options: function () { return call('OPTIONS', base + '/' + document.getElementById('noteId').value); },
                wrong: function () { return call('DELETE', base); },
                putpartial: function () { return call('PUT', base + '/' + document.getElementById('noteId').value, { title: document.getElementById('title').value }); }
            };
            document.querySelectorAll('[data-op]').forEach(function (b) { b.addEventListener('click', async function () { await OPS[b.dataset.op](); refresh(); }); });
            document.getElementById('reset').addEventListener('click', async function () { await fetch(base + '/reset', { method: 'POST' }); wire.add('sys', 'data reset'); refresh(); });
        }

        /* ================================================================ */
        if (page === 'status-codes') {
            var chips = document.getElementById('codes');
            fetch('/lab/api/basics/status').then(function (r) { return r.json(); }).then(function (d) {
                d.codes.forEach(function (c) {
                    var b = Lab.el('button', 'btn btn--small ' + (c.code >= 500 ? 'btn--danger' : c.code >= 400 ? 'btn--secondary' : ''), String(c.code));
                    b.type = 'button'; b.title = c.reason;
                    b.addEventListener('click', function () { ask(c); });
                    chips.appendChild(b);
                });
            });
            async function ask(c) {
                var url = '/lab/api/basics/status/' + c.code;
                wire.add('out', 'GET ' + url);
                var t0 = performance.now();
                var r = await fetch(url, { cache: 'no-store' }); var text = await r.text();
                var ms = Math.round(performance.now() - t0);
                var companions = ['location', 'www-authenticate', 'allow', 'retry-after', 'etag', 'x-explain'].filter(function (h) { return r.headers.get(h) !== null; }).map(function (h) { return h + ': ' + r.headers.get(h); });
                wire.add(r.ok ? 'in' : 'err', 'HTTP ' + r.status + ' ' + r.statusText + (r.redirected ? '  ← fetch() followed a ' + c.code + ' redirect to ' + new URL(r.url).pathname : '') + (companions.length ? '\n' + companions.join('\n') : ''), ms + ' ms · response.ok = ' + r.ok);
                var ex = document.getElementById('explain'); clear(ex);
                var kind = c.code < 300 ? 'success' : c.code < 400 ? 'warn' : 'error';
                ex.appendChild(UI.alert(kind, c.code + ' ' + c.reason + ' — ' + c.meaning));
                if (r.redirected) ex.appendChild(Lab.el('p', 'small muted', 'You asked for ' + c.code + ' and received ' + r.status + '. The browser followed the Location header transparently; response.redirected is true and response.url is ' + r.url + '.'));
                if (companions.length) ex.appendChild(Lab.el('p', 'small muted', 'Companion header' + (companions.length > 1 ? 's' : '') + ': ' + companions.join(' · ')));
                document.getElementById('raw').textContent = rawResponse(r, text);
                document.getElementById('meta').textContent = 'response.ok = ' + r.ok + ' · ' + ms + ' ms';
            }
        }

        /* ================================================================ */
        if (page === 'headers') {
            document.getElementById('send').addEventListener('click', async function () {
                var accept = document.getElementById('accept').value, lang = document.getElementById('lang').value;
                wire.add('out', 'GET /lab/api/basics/negotiate\nAccept: ' + accept + '\nAccept-Language: ' + lang);
                var r = await fetch('/lab/api/basics/negotiate', { headers: { 'Accept': accept, 'Accept-Language': lang }, cache: 'no-store' });
                var text = await r.text(); var ctype = r.headers.get('content-type') || '';
                wire.add('in', r.status + '\nContent-Type: ' + ctype + '\nContent-Language: ' + r.headers.get('content-language') + '\nVary: ' + r.headers.get('vary'), text.length + ' B');
                document.getElementById('resHeaders').textContent = headersText(r);
                document.getElementById('meta').textContent = ctype.split(';')[0] + ' · ' + text.length + ' B';
                var out = document.getElementById('rendered'); clear(out);
                if (ctype.indexOf('text/html') === 0) {
                    // Rendered in a sandboxed frame: it is HTML the server chose to send, shown as HTML.
                    var frame = Lab.el('iframe'); frame.setAttribute('sandbox', ''); frame.style.width = '100%'; frame.style.height = '180px'; frame.style.border = '1px solid var(--border)'; frame.style.borderRadius = '8px'; frame.style.background = '#fff';
                    frame.srcdoc = text; out.appendChild(frame);
                } else {
                    out.appendChild(Lab.el('pre', 'small', text));
                }
            });
        }

        /* ================================================================ */
        if (page === 'sending-data') {
            function fields() {
                var tags = document.getElementById('tags').value.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
                return { name: document.getElementById('name').value, age: document.getElementById('age').value, tags: tags };
            }
            document.querySelectorAll('[data-enc]').forEach(function (b) {
                b.addEventListener('click', async function () {
                    var f = fields(), enc = b.dataset.enc, url = '/lab/api/basics/decode', init = { method: 'POST', cache: 'no-store' }, shown = '', label = '';
                    if (enc === 'query') {
                        var p = new URLSearchParams(); p.set('name', f.name); p.set('age', f.age); f.tags.forEach(function (t) { p.append('tags', t); });
                        url = '/lab/api/basics/echo?' + p.toString(); init = { method: 'GET', cache: 'no-store' }; shown = '(no body — the data is in the URL)\n' + url; label = 'GET ' + url;
                    } else if (enc === 'form') {
                        var p2 = new URLSearchParams(); p2.set('name', f.name); p2.set('age', f.age); f.tags.forEach(function (t) { p2.append('tags', t); });
                        init.body = p2.toString(); init.headers = { 'Content-Type': 'application/x-www-form-urlencoded' }; shown = init.body; label = 'POST ' + url + '\nContent-Type: application/x-www-form-urlencoded';
                    } else if (enc === 'json') {
                        init.body = JSON.stringify({ name: f.name, age: Number(f.age), tags: f.tags }, null, 2); init.headers = { 'Content-Type': 'application/json' }; shown = init.body; label = 'POST ' + url + '\nContent-Type: application/json';
                    } else {
                        var fd = new FormData(); fd.append('name', f.name); fd.append('age', f.age); f.tags.forEach(function (t) { fd.append('tags', t); });
                        var file = document.getElementById('file').files[0]; if (file) fd.append('file', file);
                        init.body = fd; shown = '(the browser builds this; the server echo below shows the parts)'; label = 'POST ' + url + '\nContent-Type: multipart/form-data; boundary=----WebKitFormBoundary…  (set by the browser)';
                    }
                    wire.add('out', label);
                    var r = await fetch(url, init); var d = await r.json();
                    var raw = enc === 'query' ? shown : (d.raw_body !== undefined ? d.raw_body : (d.request ? d.request.body : shown));
                    var size = enc === 'query' ? url.length - '/lab/api/basics/echo'.length + ' B in the URL' : (d.content_length || 0) + ' B body';
                    document.getElementById('rawBody').textContent = raw || shown; document.getElementById('sizeMeta').textContent = size;
                    var how = d.how_the_server_read_it || 'query string parsed into request.args — every value is a string; repeated keys become a list.';
                    document.getElementById('how').textContent = how;
                    var parsed = d.parsed !== undefined ? d.parsed : (d.request ? d.request.query : null);
                    document.getElementById('parsed').textContent = JSON.stringify(parsed, null, 2);
                    wire.add('in', r.status + ' — server parsed: ' + JSON.stringify(parsed).slice(0, 160), size);
                });
            });
        }
    });
})();
