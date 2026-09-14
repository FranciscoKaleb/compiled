(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var C = window.Chain, wire = new Lab.WireLog(document.getElementById('wire'));
        document.getElementById('pause').addEventListener('change', function (e) { wire.paused = e.target.checked; });
        document.getElementById('clearLog').addEventListener('click', function () { wire.clear(); });
        var API = '/blockchain/api/permissioned', state = null;
        var PW = { treasury: 'treasury123', dof: 'dof123', deped: 'deped123', doh: 'doh123', auditor: 'audit123' };
        document.getElementById('username').addEventListener('change', function () { document.getElementById('password').value = PW[this.value] || ''; });
        function txLine(t) { return t.tx_type + ': ' + (t.tx_type === 'allocation' ? t.sender + ' ⇒ ' + t.receiver : t.sender + ' → ' + t.receiver) + '  ₱' + C.money(t.amount) + (t.description ? '  "' + t.description + '"' : ''); }

        async function refresh(verifyToo) {
            var res = await C.api(API + '/state'); state = res.d;
            var u = state.user;
            document.getElementById('loginBox').hidden = !!u; document.getElementById('userBox').hidden = !u;
            document.getElementById('userDot').className = 'status-dot ' + (u ? 'on' : ''); document.getElementById('userState').textContent = u ? 'signed in' : 'not signed in';
            if (u) { document.getElementById('userName').textContent = u.name + ' (' + u.username + ')'; document.getElementById('userRole').textContent = u.role; document.getElementById('userValidator').hidden = !u.validator; }
            document.getElementById('txCard').style.opacity = u ? 1 : 0.55;
            var view = document.getElementById('chainView'); C.clear(view); var checks = {};
            if (verifyToo || !state.valid) { var v = await C.api(API + '/verify'); v.d.blocks.forEach(function (b) { checks[b.height] = b; }); if (verifyToo) C.verifyReport(document.getElementById('verifyOut'), v.d); }
            state.blocks.slice().reverse().forEach(function (b) { view.appendChild(C.blockCard(b, checks[b.height], { txLine: txLine })); });
            document.getElementById('chainMeta').textContent = 'height ' + (state.blocks.length - 1) + ' · ' + (state.valid ? 'valid' : 'INVALID'); document.getElementById('validDot').className = 'status-dot ' + (state.valid ? 'on' : 'off');
            var mp = document.getElementById('mempool'); C.clear(mp);
            state.mempool.forEach(function (t) { var row = C.el('div', 'tx'); row.appendChild(C.el('span', null, txLine(t))); row.appendChild(C.el('span', 'muted', 'sig ' + t.signature.slice(0, 8) + '…')); mp.appendChild(row); });
            if (!state.mempool.length) mp.appendChild(C.el('span', 'small muted', 'nothing pending'));
            document.getElementById('mempoolCount').textContent = state.mempool.length;
            var body = document.getElementById('balances'); C.clear(body);
            state.participants.forEach(function (p) {
                var tr = C.el('tr'); var name = C.el('td', 'key', p.username); if (p.role === 'agency') { name.style.cursor = 'pointer'; name.style.textDecoration = 'underline'; name.addEventListener('click', function () { history(p.username); }); }
                tr.appendChild(name); tr.appendChild(C.el('td', null, p.role + (p.validator ? ' · validator' : ''))); tr.appendChild(C.el('td', null, '₱' + C.money(state.balances[p.username] || 0))); tr.appendChild(C.el('td', null, state.pending_spend[p.username] ? '−₱' + C.money(state.pending_spend[p.username]) : '')); body.appendChild(tr);
            });
            document.getElementById('totalAllocated').textContent = '₱' + C.money(state.total_allocated);
        }
        async function history(account) {
            var res = await C.api(API + '/history/' + account); var h = document.getElementById('history'); C.clear(h);
            h.appendChild(C.el('p', 'result__summary', 'Audit trail — ' + account + ' (balance ₱' + C.money(res.d.balance) + ')'));
            var table = C.el('table', 'data'); var body = C.el('tbody');
            res.d.rows.forEach(function (r) { var tr = C.el('tr'); tr.appendChild(C.el('td', 'key', '#' + r.height)); tr.appendChild(C.el('td', null, r.tx_type + ' ' + (r.delta < 0 ? '→ ' : '← ') + r.counterparty + (r.description ? ' — ' + r.description : ''))); var d = C.el('td', null, (r.delta > 0 ? '+' : '') + C.money(r.delta)); d.style.color = r.delta > 0 ? 'var(--brand-strong)' : 'var(--danger)'; tr.appendChild(d); tr.appendChild(C.el('td', null, C.money(r.balance_after))); body.appendChild(tr); });
            if (!res.d.rows.length) body.appendChild(C.el('tr')).appendChild(C.el('td', 'small muted', 'no committed activity yet'));
            table.appendChild(body); var wrap = C.el('div', 'table-wrap'); wrap.appendChild(table); h.appendChild(wrap);
        }
        document.getElementById('login').addEventListener('click', async function () {
            var res = await C.api(API + '/login', { method: 'POST', body: { username: document.getElementById('username').value, password: document.getElementById('password').value } });
            wire.add(res.r.ok ? 'in' : 'err', res.r.ok ? 'signed in as ' + res.d.user.name + ' [' + res.d.user.role + (res.d.user.validator ? ', validator' : '') + ']' : res.d.error); refresh();
        });
        document.getElementById('logout').addEventListener('click', async function () { await C.api(API + '/logout', { method: 'POST' }); wire.add('sys', 'signed out'); refresh(); });
        document.getElementById('submitTx').addEventListener('click', async function () {
            var body = { tx_type: document.getElementById('txType').value, receiver: document.getElementById('receiver').value, amount: document.getElementById('amount').value, description: document.getElementById('description').value };
            var res = await C.api(API + '/transactions', { method: 'POST', body: body }); var out = document.getElementById('txOut'); C.clear(out);
            if (!res.r.ok) { wire.add('err', res.r.status + ' ' + res.d.error); out.appendChild(UI.alert('error', res.d.error)); return; }
            wire.add('in', 'signed & pending: ' + txLine(res.d.transaction) + '\nsigned message: ' + res.d.signed_message.slice(0, 110) + '…\nsignature: ' + res.d.transaction.signature.slice(0, 32) + '…');
            out.appendChild(UI.alert('success', 'Signed with ' + res.d.transaction.sender + "'s key and added to the mempool.")); refresh();
        });
        document.getElementById('propose').addEventListener('click', async function () {
            var res = await C.api(API + '/propose', { method: 'POST' }); var out = document.getElementById('proposeOut'); C.clear(out);
            if (!res.r.ok) { wire.add('err', res.r.status + ' ' + res.d.error + (res.d.rejected ? '\n' + res.d.rejected.map(function (r) { return '  ✕ ' + r.reason; }).join('\n') : '')); out.appendChild(UI.alert('error', res.d.error)); return; }
            wire.add('in', 'block #' + res.d.block.height + ' signed by ' + res.d.block.validator + '  (' + res.d.block.transactions.length + ' tx' + (res.d.rejected.length ? ', ' + res.d.rejected.length + ' rejected' : '') + ')\nsignature ' + res.d.block.signature.slice(0, 32) + '…');
            out.appendChild(UI.alert(res.d.rejected.length ? 'warn' : 'success', res.d.note + (res.d.rejected.length ? ' Rejected during validation: ' + res.d.rejected.map(function (r) { return r.reason; }).join('; ') : ''))); refresh();
        });
        document.getElementById('verify').addEventListener('click', function () { wire.add('out', 'verify: links, hashes, Merkle roots, validator signatures, transaction signatures, replayed balances'); refresh(true); });
        document.getElementById('reset').addEventListener('click', async function () { await C.api(API + '/reset', { method: 'POST' }); wire.clear(); C.clear(document.getElementById('verifyOut')); C.clear(document.getElementById('history')); wire.add('sys', 'chain reset'); refresh(); });
        refresh();
    });
})();
