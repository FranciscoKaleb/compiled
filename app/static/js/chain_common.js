/* Shared rendering for the three blockchain pages. */
window.Chain = (function () {
    function el(t, c, x) { return Lab.el(t, c, x); }
    function clear(n) { while (n && n.firstChild) n.removeChild(n.firstChild); }
    function short(h, n) { return h ? h.slice(0, n || 12) + '…' : ''; }
    function money(v) { return Number(v).toLocaleString(undefined, { maximumFractionDigits: 8 }); }
    async function api(url, init) {
        init = init || {};
        if (init.body && typeof init.body !== 'string') { init.body = JSON.stringify(init.body); init.headers = Object.assign({ 'Content-Type': 'application/json' }, init.headers || {}); }
        var r = await fetch(url, Object.assign({ cache: 'no-store' }, init)); var d = await r.json().catch(function () { return {}; }); return { r: r, d: d };
    }
    /* Render a hash with its leading zeros highlighted (proof of work made visible). */
    function hashNode(hash, cls) {
        var n = el('div', 'block__hash' + (cls ? ' ' + cls : ''));
        var zeros = (hash.match(/^0*/) || [''])[0];
        if (zeros.length) n.appendChild(el('b', null, zeros));
        n.appendChild(document.createTextNode(hash.slice(zeros.length)));
        return n;
    }
    /* One block card. opts.txLine(tx) -> string, opts.badTx(tx) -> bool */
    function blockCard(b, check, opts) {
        opts = opts || {};
        var card = el('div', 'block' + (b.height === 0 ? ' is-genesis' : '') + (check && !check.valid ? ' is-bad' : ''));
        var head = el('div', 'block__head');
        head.appendChild(el('span', 'block__title', b.height === 0 ? 'Genesis' : 'Block #' + b.height));
        var right = el('span', 'small muted', (b.tx_count !== undefined ? b.tx_count : (b.transactions || []).length) + ' tx' + (b.tampered ? '  · TAMPERED' : ''));
        if (b.tampered) right.style.color = 'var(--danger)';
        head.appendChild(right); card.appendChild(head);
        card.appendChild(hashNode(b.hash));
        var meta = el('div', 'block__meta');
        if (b.nonce !== undefined && b.height > 0) meta.appendChild(el('span', null, 'nonce ' + b.nonce));
        if (b.difficulty !== undefined && b.height > 0) meta.appendChild(el('span', null, 'difficulty ' + b.difficulty));
        if (b.attempts) meta.appendChild(el('span', null, b.attempts.toLocaleString() + ' attempts'));
        if (b.mined_in) meta.appendChild(el('span', null, b.mined_in + ' s'));
        if (b.validator && b.height > 0) meta.appendChild(el('span', null, 'signed by ' + b.validator));
        if (b.miner) meta.appendChild(el('span', null, 'mined by ' + (opts.label ? opts.label(b.miner) : short(b.miner, 10))));
        if (b.reward) meta.appendChild(el('span', null, 'reward ' + money(b.reward)));
        meta.appendChild(el('span', null, b.timestamp)); card.appendChild(meta);
        if (check && !check.valid) {
            var bad = Object.keys(check.checks).filter(function (k) { return !check.checks[k]; });
            var warn = el('div', 'small', '✕ fails: ' + bad.join(', ')); warn.style.color = 'var(--danger)'; warn.style.marginTop = '4px'; card.appendChild(warn);
        }
        if (b.transactions && b.transactions.length && opts.txLine) {
            var list = el('div', 'block__txs');
            b.transactions.forEach(function (t) {
                var row = el('div', 'tx' + (opts.isCoinbase && opts.isCoinbase(t) ? ' is-coinbase' : ''));
                row.appendChild(el('span', null, opts.txLine(t))); row.appendChild(el('span', 'muted', short(t.txid, 10)));
                list.appendChild(row);
            });
            card.appendChild(list);
        }
        return card;
    }
    function verifyReport(node, v) {
        clear(node);
        node.appendChild(UI.alert(v.valid ? 'success' : 'error', v.valid ? 'Every block passes every check.' : 'Chain is INVALID from block ' + v.first_invalid_height + '.'));
        var rows = el('div', 'table-wrap'); rows.style.marginTop = 'var(--space-3)';
        var table = el('table', 'data'); var body = el('tbody');
        var names = Object.keys(v.blocks[0].checks);
        var head = el('thead'); var hr = el('tr'); hr.appendChild(el('th', null, '#')); names.forEach(function (n) { hr.appendChild(el('th', null, n.replace(/_/g, ' '))); }); head.appendChild(hr); table.appendChild(head);
        v.blocks.forEach(function (b) {
            var tr = el('tr', b.valid ? null : 'is-sensitive'); tr.appendChild(el('td', 'key', b.height));
            names.forEach(function (n) { var td = el('td', null, b.checks[n] ? '✓' : '✕'); td.style.color = b.checks[n] ? 'var(--brand-strong)' : 'var(--danger)'; tr.appendChild(td); });
            body.appendChild(tr);
        });
        table.appendChild(body); rows.appendChild(table); node.appendChild(rows);
        if (v.balance_problems && v.balance_problems.length) node.appendChild(el('p', 'small', 'Balance problems: ' + v.balance_problems.join('; ')));
    }
    return { el: el, clear: clear, short: short, money: money, api: api, hashNode: hashNode, blockCard: blockCard, verifyReport: verifyReport };
})();
