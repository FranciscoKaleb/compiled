/* Level 6 — data layer. One section per page, picked by LAB_PAGE. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var page = window.LAB_PAGE;
        var wire = new Lab.WireLog(document.getElementById('wire'), 500);
        var sqlCount = document.getElementById('sqlCount'), totalSql = 0;
        document.getElementById('pause').addEventListener('change', function (e) { wire.paused = e.target.checked; });
        document.getElementById('clearLog').addEventListener('click', function () { wire.clear(); totalSql = 0; sqlCount.textContent = '0 statements'; });
        function tile(v, l, c) { var t = Lab.el('div', 'stat-tile' + (c ? ' ' + c : '')); t.appendChild(Lab.el('div', 'stat-tile__value', v)); t.appendChild(Lab.el('div', 'stat-tile__label', l)); return t; }
        function setTiles(node, tiles) { while (node.firstChild) node.removeChild(node.firstChild); tiles.forEach(function (t) { node.appendChild(tile(t[0], t[1], t[2])); }); }
        function clear(n) { while (n && n.firstChild) n.removeChild(n.firstChild); }
        function showSql(d, label) {
            if (label) wire.add('sys', label);
            (d.sql || []).forEach(function (q) {
                var dir = /^(UPDATE|INSERT|DELETE|ALTER|CREATE|DROP)/i.test(q.sql) ? 'out' : 'in';
                wire.add(dir, q.sql, q.params && q.params !== '()' && q.params !== '{}' && q.params !== '[]' ? q.params : '');
            });
            totalSql += (d.sql || []).length; sqlCount.textContent = totalSql + ' statements';
        }
        async function api(url, init) {
            init = init || {};
            if (init.body && typeof init.body !== 'string') { init.body = JSON.stringify(init.body); init.headers = Object.assign({ 'Content-Type': 'application/json' }, init.headers || {}); }
            var r = await fetch(url, Object.assign({ cache: 'no-store' }, init)); var d = await r.json().catch(function () { return {}; }); return { r: r, d: d };
        }

        /* ================================================================ */
        if (page === 'locking') {
            var mode = document.getElementById('mode'), loaded = { A: null, B: null };
            function truth(acc) { setTiles(document.getElementById('truth'), [[acc.balance, 'balance in the DB'], [acc.version, 'version'], [acc.locked_by ? acc.locked_by + ' (' + acc.lock_seconds_left + ' s)' : 'nobody', 'lock held by'], [acc.updated_by || '—', 'last saved by']]); }
            async function refreshTruth() { var res = await api('/lab/api/data/account'); truth(res.d.account); }
            function applyMode() { var p = mode.value === 'pessimistic'; ['A', 'B'].forEach(function (w) { document.querySelector('[data-lock="' + w + '"]').hidden = !p; }); }
            mode.addEventListener('change', applyMode); applyMode(); refreshTruth(); setInterval(refreshTruth, 3000);

            document.querySelectorAll('[data-load]').forEach(function (b) {
                b.addEventListener('click', async function () {
                    var who = b.dataset.load; var res = await api('/lab/api/data/account'); showSql(res.d, who + ' loads the row');
                    loaded[who] = res.d.account; document.getElementById('ver' + who).textContent = res.d.account.version;
                    var input = document.getElementById('bal' + who); input.value = res.d.account.balance; input.disabled = false;
                    document.querySelector('[data-save="' + who + '"]').disabled = false; document.getElementById('state' + who).textContent = 'loaded v' + res.d.account.version;
                    clear(document.getElementById('msg' + who)); truth(res.d.account);
                });
            });
            document.querySelectorAll('[data-lock]').forEach(function (b) {
                b.addEventListener('click', async function () {
                    var who = b.dataset.lock; var res = await api('/lab/api/data/account/lock', { method: 'POST', body: { holder: who } });
                    showSql(res.d, who + ' asks for the lock'); var m = document.getElementById('msg' + who); clear(m);
                    m.appendChild(UI.alert(res.r.ok ? 'success' : 'error', res.d.message || res.d.error)); truth(res.d.account);
                });
            });
            document.querySelectorAll('[data-save]').forEach(function (b) {
                b.addEventListener('click', async function () {
                    var who = b.dataset.save; var body = { mode: mode.value, holder: who, balance: document.getElementById('bal' + who).value, version: loaded[who] ? loaded[who].version : -1 };
                    var res = await api('/lab/api/data/account', { method: 'POST', body: body });
                    showSql(res.d, who + ' saves (' + mode.value + ')' + (mode.value === 'optimistic' ? ' with version ' + body.version : ''));
                    var m = document.getElementById('msg' + who); clear(m);
                    m.appendChild(UI.alert(res.r.ok ? 'success' : (res.d.conflict ? 'warn' : 'error'), (res.r.ok ? '' : 'HTTP ' + res.r.status + ' — ') + (res.d.message || res.d.error)));
                    if (res.r.ok) { loaded[who] = res.d.account; document.getElementById('ver' + who).textContent = res.d.account.version; document.getElementById('state' + who).textContent = 'saved v' + res.d.account.version; }
                    else document.getElementById('state' + who).textContent = 'stale — reload';
                    truth(res.d.account);
                });
            });
            document.getElementById('reset').addEventListener('click', async function () { var res = await api('/lab/api/data/reset'); showSql({ sql: [] }, 'lab.db reseeded'); ['A', 'B'].forEach(function (w) { loaded[w] = null; document.getElementById('ver' + w).textContent = '—'; document.getElementById('bal' + w).value = ''; document.getElementById('bal' + w).disabled = true; document.querySelector('[data-save="' + w + '"]').disabled = true; document.getElementById('state' + w).textContent = 'not loaded'; clear(document.getElementById('msg' + w)); }); refreshTruth(); });
        }

        /* ================================================================ */
        if (page === 'n-plus-one') {
            var best = {}, statsNode = document.getElementById('stats');
            function render() { setTiles(statsNode, [[best.lazy ? best.lazy.q : '—', 'lazy: queries', 'stat-tile--bad'], [best.selectin ? best.selectin.q : '—', 'selectin: queries', 'stat-tile--good'], [best.joined ? best.joined.q : '—', 'joined: queries', 'stat-tile--good'], [best.lazy ? best.lazy.ms + ' ms' : '—', 'lazy: time'], [best.selectin ? best.selectin.ms + ' ms' : '—', 'selectin: time'], [best.joined ? best.joined.ms + ' ms' : '—', 'joined: time']]); }
            render();
            document.querySelectorAll('[data-load]').forEach(function (b) {
                b.addEventListener('click', async function () {
                    var load = b.dataset.load; wire.clear(); totalSql = 0;
                    var res = await api('/lab/api/data/authors?load=' + load);
                    showSql(res.d, 'load=' + load + ' → ' + res.d.sql_count + ' statement(s) in ' + res.d.ms + ' ms');
                    best[load] = { q: res.d.sql_count, ms: res.d.ms }; render();
                    var body = document.getElementById('authors'); clear(body);
                    res.d.authors.forEach(function (a) { var tr = Lab.el('tr'); tr.appendChild(Lab.el('td', 'key', a.name)); tr.appendChild(Lab.el('td', null, a.books.join(' · '))); body.appendChild(tr); });
                    document.getElementById('resultMeta').textContent = res.d.authors.length + ' authors, ' + res.d.authors.reduce(function (n, a) { return n + a.books.length; }, 0) + ' books';
                });
            });
        }

        /* ================================================================ */
        if (page === 'pagination') {
            var mode = document.getElementById('mode'), seen = {}, order = 0, cursor = null, pageNo = 0, dups = 0, statsNode = document.getElementById('stats');
            function render() { setTiles(statsNode, [[Object.keys(seen).length, 'unique items seen'], [dups, 'duplicates shown', dups ? 'stat-tile--bad' : 'stat-tile--good'], [pageNo, 'pages loaded']]); }
            function resetView() { seen = {}; order = 0; cursor = null; pageNo = 0; dups = 0; clear(document.getElementById('items')); clear(document.getElementById('dupWarn')); document.getElementById('next').disabled = true; render(); }
            resetView(); mode.addEventListener('change', resetView);
            async function load(first) {
                var url = '/lab/api/data/items?mode=' + mode.value + '&size=10';
                if (mode.value === 'offset') url += '&page=' + (first ? 1 : pageNo + 1); else if (!first && cursor) url += '&cursor=' + encodeURIComponent(cursor);
                var res = await api(url); showSql(res.d, 'GET ' + url);
                pageNo = mode.value === 'offset' ? res.d.page : pageNo + 1; cursor = res.d.next_cursor || null;
                var body = document.getElementById('items'), pageDups = [];
                res.d.items.forEach(function (it) {
                    var dup = seen[it.id] !== undefined; if (dup) { dups += 1; pageDups.push(it.title); } else seen[it.id] = ++order;
                    var tr = Lab.el('tr', dup ? 'is-sensitive' : null); tr.appendChild(Lab.el('td', 'key', dup ? 'dup!' : String(seen[it.id]))); tr.appendChild(Lab.el('td', null, it.id)); tr.appendChild(Lab.el('td', null, it.title)); tr.appendChild(Lab.el('td', null, it.created_at)); body.appendChild(tr);
                });
                body.parentNode.parentNode.scrollTop = body.parentNode.parentNode.scrollHeight;
                var w = document.getElementById('dupWarn'); clear(w);
                if (pageDups.length) w.appendChild(UI.alert('error', 'Page ' + pageNo + ' repeated ' + pageDups.length + ' item(s) you already saw: ' + pageDups.join(', ') + '. The insert shifted every offset by one.'));
                document.getElementById('pageMeta').textContent = mode.value === 'offset' ? 'page ' + res.d.page + ' of ' + res.d.pages + ' · ' + res.d.total + ' rows' : 'cursor page ' + pageNo + ' · ' + res.d.total + ' rows' + (cursor ? '' : ' · end');
                document.getElementById('next').disabled = mode.value === 'offset' ? res.d.page >= res.d.pages : !cursor; render();
            }
            document.getElementById('first').addEventListener('click', function () { resetView(); load(true); });
            document.getElementById('next').addEventListener('click', function () { load(false); });
            document.getElementById('insert').addEventListener('click', async function () { var res = await api('/lab/api/data/items', { method: 'POST' }); showSql(res.d, 'someone else: ' + res.d.message + ' (' + res.d.item.title + ')'); });
            document.getElementById('reset').addEventListener('click', async function () { await api('/lab/api/data/reset'); resetView(); wire.add('sys', 'lab.db reseeded'); });
        }

        /* ================================================================ */
        if (page === 'migrations') {
            var timer = null, ok = 0, failed = 0, statsNode = document.getElementById('stats');
            function render() { setTiles(statsNode, [[ok, 'requests OK', 'stat-tile--good'], [failed, 'requests FAILED', failed ? 'stat-tile--bad' : '']]); }
            render();
            async function schema(d) {
                if (!d) { var res = await api('/lab/api/data/schema'); d = res.d; if (d.app_alembic_version) { document.getElementById('alembic').textContent = 'For context, the app\'s own database is at Alembic revision ' + d.app_alembic_version + '.'; document.getElementById('alembicInline').textContent = d.app_alembic_version; } }
                var body = document.getElementById('columns'); clear(body);
                d.columns.forEach(function (c) { var tr = Lab.el('tr'); tr.appendChild(Lab.el('td', 'key', c.name)); tr.appendChild(Lab.el('td', null, c.type)); tr.appendChild(Lab.el('td', null, c.nullable ? 'yes' : 'NOT NULL')); if (c.name === 'phone') tr.style.color = c.nullable ? 'var(--warning)' : 'var(--brand-strong)'; body.appendChild(tr); });
                document.getElementById('rowCount').textContent = d.count + ' rows'; document.getElementById('sample').textContent = JSON.stringify(d.rows, null, 1);
            }
            schema();
            async function tick() {
                var res = await api('/lab/api/data/traffic', { method: 'POST' });
                if (res.r.ok) { ok += 1; wire.add('in', 'traffic: read #' + (res.d.read ? res.d.read.id : '?') + ', inserted one' + (res.d.columns.indexOf('phone') !== -1 ? ' (new code path: writing phone)' : ' (old code path)'), res.d.count + ' rows'); }
                else { failed += 1; wire.add('err', 'traffic FAILED: ' + (res.d.error || res.r.status)); }
                document.getElementById('trafficDot').className = 'status-dot ' + (res.r.ok ? 'on' : 'off'); render();
            }
            document.getElementById('startTraffic').addEventListener('click', function () { timer = setInterval(tick, 1000); tick(); document.getElementById('trafficState').textContent = 'running'; document.getElementById('startTraffic').disabled = true; document.getElementById('stopTraffic').disabled = false; });
            document.getElementById('stopTraffic').addEventListener('click', function () { clearInterval(timer); timer = null; document.getElementById('trafficState').textContent = 'stopped'; document.getElementById('trafficDot').className = 'status-dot'; document.getElementById('startTraffic').disabled = false; document.getElementById('stopTraffic').disabled = true; });
            document.querySelectorAll('[data-step]').forEach(function (b) {
                b.addEventListener('click', async function () {
                    var res = await api('/lab/api/data/migrate', { method: 'POST', body: { step: b.dataset.step } });
                    showSql(res.d, 'migration step: ' + b.dataset.step);
                    var m = document.getElementById('migrateMsg'); clear(m); m.appendChild(UI.alert(res.r.ok ? 'success' : 'error', res.d.note || res.d.error));
                    if (res.r.ok) schema(res.d); else schema();
                });
            });
            window.addEventListener('pagehide', function () { if (timer) clearInterval(timer); });
        }
    });
})();
