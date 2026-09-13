/* Level 3 — server patterns. One section per page, picked by LAB_PAGE. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var page = window.LAB_PAGE;
        var wire = new Lab.WireLog(document.getElementById('wire'));
        document.getElementById('pause').addEventListener('change', function (e) { wire.paused = e.target.checked; });
        document.getElementById('clearLog').addEventListener('click', function () { wire.clear(); });

        function tile(v, l, c) { var t = Lab.el('div', 'stat-tile' + (c ? ' ' + c : '')); t.appendChild(Lab.el('div', 'stat-tile__value', v)); t.appendChild(Lab.el('div', 'stat-tile__label', l)); return t; }
        function setTiles(node, tiles) { while (node.firstChild) node.removeChild(node.firstChild); tiles.forEach(function (t) { node.appendChild(tile(t[0], t[1], t[2])); }); }
        function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
        function row(cells, cls) { var tr = Lab.el('tr', cls); cells.forEach(function (c, i) { tr.appendChild(Lab.el('td', i === 0 ? 'key' : 'value', c)); }); return tr; }
        async function post(url, body, headers) {
            var init = { method: 'POST', headers: Object.assign({ 'Content-Type': 'application/json' }, headers || {}) };
            if (body !== undefined) init.body = JSON.stringify(body);
            var r = await fetch(url, init); var d = await r.json().catch(function () { return {}; }); return { r: r, d: d };
        }

        /* ================================================================ */
        if (page === 'background-jobs') {
            var dot = document.getElementById('dot'), bar = document.getElementById('bar'), msg = document.getElementById('message'), state = document.getElementById('jobState'), jobIdEl = document.getElementById('jobId');
            var startB = document.getElementById('start'), cancelB = document.getElementById('cancel'), stepsIn = document.getElementById('steps');
            stepsIn.addEventListener('input', function () { document.querySelector('output[for="steps"]').textContent = stepsIn.value; });
            var current = null, poller = null, source = null;

            function paint(job) {
                var pct = job.total ? job.progress / job.total * 100 : 0;
                bar.style.width = pct + '%';
                bar.style.background = job.status === 'failed' ? 'var(--danger)' : job.status === 'cancelled' ? 'var(--warning)' : '';
                msg.textContent = job.status + ' — ' + (job.message || '') + (job.error ? ' (' + job.error + ')' : '');
                dot.className = 'status-dot ' + ({ queued: 'wait', running: 'on', done: 'on', failed: 'off', cancelled: 'off' }[job.status] || '');
                state.textContent = JSON.stringify(job, null, 2);
                if (['done', 'failed', 'cancelled'].indexOf(job.status) !== -1) finish();
            }
            function finish() { if (poller) clearInterval(poller); if (source) source.close(); poller = source = null; startB.disabled = false; cancelB.disabled = true; }

            startB.addEventListener('click', async function () {
                startB.disabled = true; cancelB.disabled = false;
                var steps = parseInt(stepsIn.value, 10);
                var body = { steps: steps, fail_at: document.getElementById('failAt').checked ? Math.ceil(steps / 2) : null };
                wire.add('out', 'POST /lab/api/server/jobs ' + JSON.stringify(body));
                var t0 = performance.now();
                var res = await post('/lab/api/server/jobs', body);
                wire.add('in', res.r.status + ' ' + res.r.statusText + '\nLocation: ' + res.r.headers.get('Location'), Math.round(performance.now() - t0) + ' ms — the request returned before any work happened');
                current = res.d.job_id; jobIdEl.textContent = current;
                var mode = document.getElementById('follow').value;
                if (mode === 'poll') {
                    poller = setInterval(async function () {
                        wire.add('out', 'GET ' + res.d.status_url);
                        var r = await fetch(res.d.status_url); var d = await r.json();
                        wire.add('in', d.job.status + ' ' + d.job.progress + '/' + d.job.total);
                        paint(d.job);
                    }, 1000);
                } else {
                    wire.add('out', 'GET ' + res.d.status_url + '/events   (EventSource)');
                    source = new EventSource(res.d.status_url + '/events');
                    source.addEventListener('progress', function (e) { var d = JSON.parse(e.data); wire.add('in', 'event: progress  ' + d.status + ' ' + d.progress + '/' + d.total); paint(d); });
                    source.onerror = function () { wire.add('sys', 'stream closed'); };
                }
            });
            cancelB.addEventListener('click', async function () {
                wire.add('out', 'POST /lab/api/server/jobs/' + current + '/cancel');
                await post('/lab/api/server/jobs/' + current + '/cancel');
            });
        }

        /* ================================================================ */
        if (page === 'rate-limiting') {
            var stats = { sent: 0, ok: 0, limited: 0 }, statsNode = document.getElementById('stats');
            var algoSel = document.getElementById('algo'), steadyTimer = null;
            function render() { setTiles(statsNode, [[stats.sent, 'sent'], [stats.ok, '200 served', 'stat-tile--good'], [stats.limited, '429 limited', stats.limited ? 'stat-tile--bad' : '']]); }
            render();
            async function hit() {
                stats.sent += 1;
                var url = '/lab/api/server/limited?algo=' + algoSel.value;
                var r = await fetch(url, { cache: 'no-store' }); var d = await r.json();
                var hdr = ['RateLimit-Limit', 'RateLimit-Remaining', 'Retry-After'].filter(function (h) { return r.headers.get(h) !== null; }).map(function (h) { return h + ': ' + r.headers.get(h); }).join('  ');
                if (r.status === 429) { stats.limited += 1; wire.add('err', '429 Too Many Requests — wait ' + d.retry_after_s + 's', hdr); }
                else { stats.ok += 1; wire.add('in', '200 served', hdr); }
                render(); refresh();
            }
            async function refresh() {
                var d = await (await fetch('/lab/api/server/limited/state')).json();
                var b = d.bucket; document.getElementById('bucketBar').firstElementChild.style.width = (b.tokens / b.capacity * 100) + '%';
                document.getElementById('bucketText').textContent = b.tokens.toFixed(2) + ' / ' + b.capacity + ' tokens · +' + b.refill_per_s + '/s';
                var chips = document.getElementById('windowChips'); clear(chips);
                d.window.ages.forEach(function (age) { chips.appendChild(Lab.el('span', 'chip', (d.window.seconds - age).toFixed(1) + 's left')); });
                if (!d.window.ages.length) chips.appendChild(Lab.el('span', 'small muted', 'empty'));
            }
            setInterval(refresh, 500); refresh();
            document.getElementById('one').addEventListener('click', hit);
            document.getElementById('spam').addEventListener('click', function () { wire.add('sys', '12 requests fired at once'); for (var i = 0; i < 12; i++) hit(); });
            document.getElementById('steady').addEventListener('click', function (e) {
                if (steadyTimer) { clearInterval(steadyTimer); steadyTimer = null; e.target.textContent = 'Steady 1 / s'; return; }
                steadyTimer = setInterval(hit, 1000); e.target.textContent = 'Stop steady';
            });
            document.getElementById('reset').addEventListener('click', async function () { await post('/lab/api/server/limited/reset'); stats = { sent: 0, ok: 0, limited: 0 }; render(); wire.clear(); refresh(); });
        }

        /* ================================================================ */
        if (page === 'idempotency') {
            var key = null, statsNode = document.getElementById('stats'), keyEl = document.getElementById('key'), useKey = document.getElementById('useKey');
            function newKey() { key = 'order_' + crypto.randomUUID(); keyEl.textContent = 'Idempotency-Key: ' + key; }
            newKey();
            async function ledger() {
                var d = await (await fetch('/lab/api/server/pay/ledger')).json();
                setTiles(statsNode, [[d.count, 'charges on record', d.count > 1 ? 'stat-tile--bad' : ''], ['$' + d.total.toFixed(2), 'total charged']]);
                var body = document.getElementById('ledger'); clear(body);
                d.charges.forEach(function (c) { body.appendChild(row([c.charge_id, '$' + c.amount.toFixed(2), c.idempotency_key || '(none)'])); });
            }
            ledger();
            async function pay(tag) {
                var headers = useKey.checked ? { 'Idempotency-Key': key } : {};
                wire.add('out', 'POST /lab/api/server/pay {"amount": 25}' + (useKey.checked ? '\nIdempotency-Key: ' + key : '\n(no Idempotency-Key)'), tag);
                var t0 = performance.now();
                var res = await post('/lab/api/server/pay', { amount: 25 }, headers);
                wire.add(res.d.replayed ? 'sys' : 'in', (res.d.replayed ? 'replayed earlier result — no new charge' : 'NEW charge ' + res.d.charge.charge_id) + (res.r.headers.get('Idempotent-Replayed') ? '\nIdempotent-Replayed: true' : ''), Math.round(performance.now() - t0) + ' ms');
                ledger();
            }
            document.getElementById('pay').addEventListener('click', function () { pay('click'); });
            document.getElementById('double').addEventListener('click', function () { pay('click 1 of 2'); pay('click 2 of 2'); });
            document.getElementById('newOrder').addEventListener('click', function () { newKey(); wire.add('sys', 'new order → new key'); });
            document.getElementById('resetLedger').addEventListener('click', async function () { await post('/lab/api/server/pay/reset'); newKey(); ledger(); wire.clear(); });
        }

        /* ================================================================ */
        if (page === 'webhooks') {
            var urlIn = document.getElementById('url'), secretIn = document.getElementById('secret');
            urlIn.value = location.origin + '/lab/api/server/webhooks/inbox';
            async function refresh() {
                var d = await (await fetch('/lab/api/server/webhooks/log')).json();
                if (!secretIn.value) secretIn.value = d.secret;
                var a = document.getElementById('attempts'); clear(a);
                d.deliveries.forEach(function (x) {
                    var tr = row([x.delivery_id, '#' + x.attempt, (x.status ? 'HTTP ' + x.status : (x.error || 'no response')) + ' → ' + x.outcome, x.ms + ' ms']);
                    if (x.outcome === 'delivered') tr.style.color = 'var(--brand-strong)'; else if (x.outcome === 'gave up') tr.style.color = 'var(--danger)';
                    a.appendChild(tr);
                });
                var i = document.getElementById('inbox'); clear(i);
                d.inbox.forEach(function (x) {
                    var tr = row([x.delivery_id || '?', '#' + x.attempt, (x.verified ? '✓ valid' : '✕ ' + x.reason), String(x.responded)]);
                    if (!x.verified) tr.className = 'is-sensitive';
                    i.appendChild(tr);
                });
                document.getElementById('fail').checked = d.mode.fail; document.getElementById('slow').checked = d.mode.slow;
            }
            refresh(); setInterval(refresh, 1000);
            document.getElementById('send').addEventListener('click', async function () {
                var body = { url: urlIn.value, secret: secretIn.value };
                wire.add('out', 'POST /lab/api/server/webhooks/send → server will POST to ' + body.url);
                var res = await post('/lab/api/server/webhooks/send', body);
                if (!res.d.ok) { wire.add('err', res.d.error); return; }
                wire.add('sys', 'delivery ' + res.d.delivery_id + ' queued for event ' + res.d.event.id + '. Watch the tables — retries arrive over ~7 s.');
            });
            ['fail', 'slow'].forEach(function (k) {
                document.getElementById(k).addEventListener('change', async function (e) {
                    var b = {}; b[k] = e.target.checked; await post('/lab/api/server/webhooks/inbox/mode', b);
                    wire.add('sys', 'receiver ' + k + ' = ' + e.target.checked);
                });
            });
            document.getElementById('reset').addEventListener('click', async function () { await post('/lab/api/server/webhooks/reset'); wire.clear(); refresh(); });
        }

        /* ================================================================ */
        if (page === 'cancellation') {
            var q = document.getElementById('q'), strategy = document.getElementById('strategy'), results = document.getElementById('results'), shownFor = document.getElementById('shownFor'), warn = document.getElementById('staleWarn'), statsNode = document.getElementById('stats');
            var stats = { sent: 0, applied: 0, stale: 0, aborted: 0 }, timer = null, controller = null, latestQuery = '';
            function render() { setTiles(statsNode, [[stats.sent, 'requests sent'], [stats.applied, 'results shown'], [stats.stale, 'stale overwrote', stats.stale ? 'stat-tile--bad' : ''], [stats.aborted, 'aborted', 'stat-tile--good']]); }
            render();
            async function search(query) {
                stats.sent += 1; render();
                var init = { cache: 'no-store' };
                if (strategy.value === 'cancel') { if (controller) { controller.abort(); } controller = new AbortController(); init.signal = controller.signal; }
                wire.add('out', 'GET /lab/api/server/search?q=' + query);
                try {
                    var r = await fetch('/lab/api/server/search?q=' + encodeURIComponent(query), init); var d = await r.json();
                    var stale = d.q !== latestQuery;
                    wire.add(stale ? 'err' : 'in', 'results for "' + d.q + '"' + (stale ? '  ← STALE: box now says "' + latestQuery + '" — but naive code shows it anyway' : ''), d.took_ms + ' ms');
                    clear(results); d.results.forEach(function (w) { results.appendChild(Lab.el('span', 'chip', w)); });
                    if (!d.results.length) results.appendChild(Lab.el('span', 'small muted', d.q ? 'no matches' : ''));
                    shownFor.textContent = 'showing results for "' + d.q + '"';
                    clear(warn);
                    if (stale) { stats.stale += 1; warn.appendChild(UI.alert('error', 'Wrong results on screen: these are for "' + d.q + '" but you typed "' + latestQuery + '".')); }
                    stats.applied += 1; render();
                } catch (e) {
                    if (e.name === 'AbortError') { stats.aborted += 1; wire.add('sys', 'aborted request for "' + query + '" — it will never overwrite anything'); render(); }
                    else wire.add('err', e.message);
                }
            }
            q.addEventListener('input', function () {
                latestQuery = q.value.trim().toLowerCase();
                if (strategy.value === 'naive') { search(latestQuery); return; }
                clearTimeout(timer); timer = setTimeout(function () { search(latestQuery); }, 300);
            });
            document.getElementById('autoType').addEventListener('click', function () {
                var word = 'strawberry', i = 0; q.value = '';
                var t = setInterval(function () { q.value = word.slice(0, ++i); q.dispatchEvent(new Event('input')); if (i >= word.length) clearInterval(t); }, 90);
            });
            document.getElementById('reset').addEventListener('click', async function () { await post('/lab/api/server/search/reset'); stats = { sent: 0, applied: 0, stale: 0, aborted: 0 }; render(); wire.clear(); clear(results); clear(warn); shownFor.textContent = ''; });
        }
    });
})();
