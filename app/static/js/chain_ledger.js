(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var C = window.Chain, wire = new Lab.WireLog(document.getElementById('wire'));
        document.getElementById('pause').addEventListener('change', function (e) { wire.paused = e.target.checked; });
        document.getElementById('clearLog').addEventListener('click', function () { wire.clear(); });
        var API = '/blockchain/api/ledger', state = null;
        var diff = document.getElementById('difficulty'), diffOut = document.querySelector('output[for="difficulty"]');
        function diffHelp() { var d = parseInt(diff.value, 10); document.getElementById('diffHelp').textContent = 'about ' + Math.pow(16, d).toLocaleString() + ' hash attempts on average per block'; diffOut.textContent = d; }
        diff.addEventListener('input', diffHelp); diff.addEventListener('change', async function () { await C.api(API + '/settings', { method: 'POST', body: { difficulty: parseInt(diff.value, 10) } }); wire.add('sys', 'difficulty set to ' + diff.value); });

        async function refresh(verifyToo) {
            var res = await C.api(API + '/state'); state = res.d;
            diff.value = state.settings.difficulty; diffHelp();
            var view = document.getElementById('chainView'); C.clear(view);
            var checks = {};
            if (verifyToo || !state.valid) { var v = await C.api(API + '/verify'); v.d.blocks.forEach(function (b) { checks[b.height] = b; }); if (verifyToo) C.verifyReport(document.getElementById('verifyOut'), v.d); }
            state.blocks.slice().reverse().forEach(function (b) { view.appendChild(C.blockCard(b, checks[b.height])); });
            document.getElementById('chainMeta').textContent = 'height ' + state.height + ' · ' + state.total_tx + ' records · ' + (state.valid ? 'valid' : 'INVALID from #' + state.first_invalid_height);
            document.getElementById('validDot').className = 'status-dot ' + (state.valid ? 'on' : 'off');
            var mp = document.getElementById('mempool'); C.clear(mp);
            state.mempool.forEach(function (t) { var row = C.el('div', 'tx'); row.appendChild(C.el('span', null, t.sender + ' → ' + t.receiver + '  ' + C.money(t.amount) + '  [' + t.tx_type + ']' + (t.memo ? '  "' + t.memo + '"' : ''))); row.appendChild(C.el('span', 'muted', C.short(t.txid, 10))); mp.appendChild(row); });
            if (!state.mempool.length) mp.appendChild(C.el('span', 'small muted', 'empty'));
            document.getElementById('mempoolCount').textContent = state.mempool.length + ' pending';
        }
        document.getElementById('txForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            var body = { sender: document.getElementById('sender').value, receiver: document.getElementById('receiver').value, amount: document.getElementById('amount').value, tx_type: document.getElementById('txType').value, memo: document.getElementById('memo').value };
            var res = await C.api(API + '/transactions', { method: 'POST', body: body });
            if (!res.r.ok) { wire.add('err', res.d.error); return; }
            wire.add('in', 'txid ' + C.short(res.d.transaction.txid, 16) + ' = SHA-256(' + res.d.canonical.slice(0, 80) + '…)'); refresh();
        });
        document.getElementById('mine').addEventListener('click', async function () {
            var btn = this; btn.disabled = true; btn.textContent = 'Mining…';
            wire.add('out', 'mine: searching for a nonce at difficulty ' + diff.value);
            var res = await C.api(API + '/mine', { method: 'POST', body: { max_tx: 5 } });
            btn.disabled = false; btn.textContent = '⛏ Mine a block (up to 5 tx)';
            var out = document.getElementById('mineOut'); C.clear(out);
            if (!res.r.ok) { wire.add('err', res.d.error); out.appendChild(UI.alert('error', res.d.error)); return; }
            var b = res.d.block;
            wire.add('in', 'block #' + b.height + ' found: nonce ' + b.nonce + ' after ' + b.attempts.toLocaleString() + ' attempts in ' + b.mined_in + ' s\nhash ' + b.hash);
            out.appendChild(UI.alert('success', 'Block #' + b.height + ' mined: ' + b.attempts.toLocaleString() + ' attempts, ' + b.mined_in + ' s. Header hashed: ' + res.d.header_canonical.slice(0, 60) + '…'));
            refresh();
        });
        document.getElementById('verify').addEventListener('click', function () { wire.add('out', 'verify every block'); refresh(true); });
        document.getElementById('tamper').addEventListener('click', async function () {
            var h = parseInt(document.getElementById('tamperHeight').value, 10), a = parseFloat(document.getElementById('tamperAmount').value);
            var res = await C.api(API + '/tamper', { method: 'POST', body: { height: h, amount: a } });
            var out = document.getElementById('attackOut'); C.clear(out);
            if (!res.r.ok) { out.appendChild(UI.alert('error', res.d.error)); return; }
            wire.add('err', 'stored block #' + h + ' edited: ' + res.d.changed.from + ' → ' + res.d.changed.to + '. Verify now fails at #' + res.d.verify.first_invalid_height);
            out.appendChild(UI.alert('warn', res.d.note)); refresh(true);
        });
        document.getElementById('remine').addEventListener('click', async function () {
            var h = parseInt(document.getElementById('tamperHeight').value, 10);
            wire.add('out', 'attacker re-mines blocks ' + h + '…tip');
            var res = await C.api(API + '/remine', { method: 'POST', body: { from_height: h } });
            var out = document.getElementById('attackOut'); C.clear(out);
            if (!res.r.ok) { out.appendChild(UI.alert('error', res.d.error)); return; }
            wire.add('in', res.d.redone.map(function (r) { return '#' + r.height + ': ' + r.attempts.toLocaleString() + ' attempts, ' + r.seconds + ' s'; }).join('\n'));
            out.appendChild(UI.alert('warn', res.d.note)); refresh(true);
        });
        document.getElementById('reset').addEventListener('click', async function () { await C.api(API + '/reset', { method: 'POST' }); wire.clear(); C.clear(document.getElementById('verifyOut')); C.clear(document.getElementById('attackOut')); C.clear(document.getElementById('mineOut')); wire.add('sys', 'chain reset with three seed records'); refresh(); });
        refresh();
    });
})();
