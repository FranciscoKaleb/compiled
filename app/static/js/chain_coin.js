(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var C = window.Chain, wire = new Lab.WireLog(document.getElementById('wire'));
        document.getElementById('pause').addEventListener('change', function (e) { wire.paused = e.target.checked; });
        document.getElementById('clearLog').addEventListener('click', function () { wire.clear(); });
        var API = '/blockchain/api/coin', state = null, labels = {};
        function label(a) { return labels[a] || C.short(a, 10); }
        function txLine(t) {
            if (!t.inputs.length) return 'coinbase → ' + label(t.outputs[0].address) + '  ' + C.money(t.outputs[0].amount);
            return t.inputs.length + ' in → ' + t.outputs.map(function (o) { return label(o.address) + ' ' + C.money(o.amount); }).join(' + ') + (t.fee ? '  fee ' + t.fee : '');
        }
        function fillSelect(sel, keep) { var cur = sel.value; C.clear(sel); state.wallets.forEach(function (w) { var o = C.el('option', null, w.label + ' (' + C.money(w.balance) + ')'); o.value = w.address; sel.appendChild(o); }); if (keep && cur) sel.value = cur; }

        async function refresh(verifyToo) {
            var res = await C.api(API + '/state'); state = res.d; labels = {}; state.wallets.forEach(function (w) { labels[w.address] = w.label; });
            var body = document.getElementById('wallets'); C.clear(body);
            state.wallets.forEach(function (w) {
                var tr = C.el('tr'); tr.appendChild(C.el('td', 'key', w.label)); tr.appendChild(C.el('td', 'mono small', C.short(w.address, 14)));
                tr.appendChild(C.el('td', null, C.money(w.balance) + ' ' + state.symbol + (w.pending_out ? '  (−' + C.money(w.pending_out) + ' pending)' : '')));
                var b = C.el('button', 'btn btn--secondary btn--small', 'UTXOs'); b.type = 'button'; b.addEventListener('click', function () { showWallet(w.address); }); var td = C.el('td'); td.appendChild(b); tr.appendChild(td); body.appendChild(tr);
            });
            document.getElementById('supply').textContent = 'supply ' + C.money(state.supply) + ' ' + state.symbol + ' · ' + state.utxo_count + ' UTXOs';
            ['miner', 'from', 'to'].forEach(function (id) { fillSelect(document.getElementById(id), true); });
            if (state.wallets.length > 1 && document.getElementById('to').value === document.getElementById('from').value) document.getElementById('to').selectedIndex = 1;
            document.getElementById('mineInfo').textContent = 'Next block: subsidy ' + C.money(state.next_reward) + ' ' + state.symbol + ' + fees, difficulty ' + state.next_difficulty + ' — ' + state.difficulty_note + '. Halving every ' + state.halving_interval + ' blocks.';
            var view = document.getElementById('chainView'); C.clear(view); var checks = {};
            if (verifyToo || !state.valid) { var v = await C.api(API + '/verify'); v.d.blocks.forEach(function (b) { checks[b.height] = b; }); if (verifyToo) C.verifyReport(document.getElementById('verifyOut'), v.d); }
            state.blocks.slice().reverse().forEach(function (b) { view.appendChild(C.blockCard(b, checks[b.height], { label: label })); });
            document.getElementById('chainMeta').textContent = 'height ' + (state.blocks.length - 1) + ' · ' + (state.valid ? 'valid' : 'INVALID'); document.getElementById('validDot').className = 'status-dot ' + (state.valid ? 'on' : 'off');
            var mp = document.getElementById('mempool'); C.clear(mp);
            state.mempool.forEach(function (t) { var row = C.el('div', 'tx'); row.appendChild(C.el('span', null, txLine(t))); row.appendChild(C.el('span', 'muted', C.short(t.txid, 10))); mp.appendChild(row); });
            if (!state.mempool.length) mp.appendChild(C.el('span', 'small muted', 'empty'));
            document.getElementById('mempoolCount').textContent = state.mempool.length;
            showUtxos();
        }
        async function showUtxos() {
            var all = []; for (var w of state.wallets) { var r = await C.api(API + '/wallets/' + w.address); r.d.utxos.forEach(function (u) { all.push(u); }); }
            var node = document.getElementById('utxos'); C.clear(node);
            all.sort(function (a, b) { return a.height - b.height; }).forEach(function (u) { var row = C.el('div', 'tx'); row.appendChild(C.el('span', null, label(u.address) + '  ' + C.money(u.amount) + '  (block #' + u.height + ')')); row.appendChild(C.el('span', 'muted', C.short(u.txid, 10) + ':' + u.index)); node.appendChild(row); });
            if (!all.length) node.appendChild(C.el('span', 'small muted', 'no coins exist yet — mine a block'));
            document.getElementById('utxoMeta').textContent = all.length + ' outputs';
        }
        async function showWallet(address) {
            var r = await C.api(API + '/wallets/' + address);
            wire.add('sys', label(address) + ': ' + r.d.utxos.length + ' UTXO(s) = ' + C.money(r.d.balance) + '\n' + r.d.utxos.map(function (u) { return '  ' + C.short(u.txid, 12) + ':' + u.index + '  ' + C.money(u.amount) + '  from block #' + u.height; }).join('\n'));
        }
        document.getElementById('newWallet').addEventListener('click', async function () {
            var res = await C.api(API + '/wallets', { method: 'POST', body: { label: document.getElementById('newLabel').value } });
            if (!res.r.ok) { wire.add('err', res.d.error); return; }
            wire.add('in', 'wallet "' + res.d.wallet.label + '" created\naddress    ' + res.d.wallet.address + '\npublic key ' + res.d.wallet.public_key); document.getElementById('newLabel').value = ''; refresh();
        });
        document.getElementById('mine').addEventListener('click', async function () {
            var btn = this; btn.disabled = true; btn.textContent = 'Mining…'; wire.add('out', 'mine → ' + label(document.getElementById('miner').value) + ' at difficulty ' + state.next_difficulty);
            var res = await C.api(API + '/mine', { method: 'POST', body: { miner: document.getElementById('miner').value } });
            btn.disabled = false; btn.textContent = 'Mine the next block'; var out = document.getElementById('mineOut'); C.clear(out);
            if (!res.r.ok) { wire.add('err', res.d.error); out.appendChild(UI.alert('error', res.d.error)); return; }
            wire.add('in', 'block #' + res.d.block.height + ' mined in ' + res.d.block.mined_in + ' s (' + res.d.attempts.toLocaleString() + ' attempts)\ncoinbase = subsidy ' + C.money(res.d.subsidy) + ' + fees ' + C.money(res.d.fees) + ' = ' + C.money(res.d.reward) + (res.d.rejected.length ? '\nrejected: ' + res.d.rejected.map(function (r) { return r.reason; }).join('; ') : ''));
            out.appendChild(UI.alert('success', 'Block #' + res.d.block.height + ': ' + C.money(res.d.reward) + ' ' + state.symbol + ' to ' + label(res.d.block.miner) + ' (' + C.money(res.d.subsidy) + ' subsidy + ' + C.money(res.d.fees) + ' fees). ' + res.d.difficulty_note)); refresh();
        });
        document.getElementById('send').addEventListener('click', async function () {
            var body = { from: document.getElementById('from').value, to: document.getElementById('to').value, amount: document.getElementById('amount').value, fee: document.getElementById('fee').value };
            var res = await C.api(API + '/send', { method: 'POST', body: body }); var out = document.getElementById('sendOut'); C.clear(out);
            if (!res.r.ok) { wire.add('err', res.d.error); out.appendChild(UI.alert('error', res.d.error)); return; }
            var t = res.d.transaction;
            wire.add('in', 'broadcast ' + C.short(t.txid, 14) + ': ' + res.d.note + '\ninputs  ' + t.inputs.map(function (i) { return C.short(i.txid, 10) + ':' + i.index; }).join(', ') + '\noutputs ' + t.outputs.map(function (o) { return label(o.address) + ' ' + C.money(o.amount); }).join(', ') + '\nsigned  ' + res.d.signed_message.slice(0, 90) + '…');
            out.appendChild(UI.alert('success', res.d.note + '. It is pending until a miner includes it.')); refresh();
        });
        document.getElementById('doubleSpend').addEventListener('click', async function () {
            var res = await C.api(API + '/double-spend', { method: 'POST', body: { from: document.getElementById('from').value } }); var out = document.getElementById('sendOut'); C.clear(out);
            if (!res.r.ok) { wire.add('err', res.d.error); out.appendChild(UI.alert('error', res.d.error)); return; }
            res.d.results.forEach(function (r) { wire.add(r.accepted ? 'in' : 'err', r.which + ' spend of ' + res.d.utxo + ': ' + (r.accepted ? 'ACCEPTED into the mempool' : 'REJECTED — ' + r.reason)); });
            out.appendChild(UI.alert('warn', res.d.note)); refresh();
        });
        document.getElementById('verify').addEventListener('click', function () { wire.add('out', 'verify: links, hashes, Merkle roots, PoW, one coinbase per block, coinbase ≤ subsidy + fees, every input signed & unspent'); refresh(true); });
        document.getElementById('reset').addEventListener('click', async function () { await C.api(API + '/reset', { method: 'POST' }); wire.clear(); C.clear(document.getElementById('verifyOut')); wire.add('sys', 'chain reset: two empty wallets, no coins'); refresh(); });
        refresh();
    });
})();
