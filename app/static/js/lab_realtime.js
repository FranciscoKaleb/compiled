/* Drives one transport on its demo page. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var kind = window.LAB_TRANSPORT;
        var dot = document.getElementById('dot'), stateText = document.getElementById('stateText');
        var price = document.getElementById('price'), seq = document.getElementById('seq');
        var statsNode = document.getElementById('stats');
        var wire = new Lab.WireLog(document.getElementById('wire'));
        var lastPrice = null;

        var EXPLAIN = {
            'short-polling': 'During an outage every poll fails and the client keeps hammering at the same rate. There is no notion of "a connection" to lose, so nothing to recover either — it just starts working again.',
            'long-polling': 'The held request fails immediately with 503 and the client backs off exponentially before asking again. Missed events are recovered because the client tells the server the last seq it saw.',
            'sse': 'The stream ends; EventSource waits (see "retry: 2000") and reconnects on its own, sending Last-Event-ID so the server replays everything you missed from its buffer. You wrote no reconnect code.',
            'websocket': 'The socket closes with code 1013 ("try again later"). Unlike SSE, the browser does nothing — the reconnect loop and backoff here are hand-written, and any messages during the gap are lost unless you build replay yourself.'
        };
        document.getElementById('explain').textContent = EXPLAIN[kind] || '';

        var hooks = {
            onEvent: function (ev) {
                if (ev.kind === 'tick') {
                    price.textContent = ev.price.toFixed(2);
                    price.className = 'ticker__price ' + (lastPrice === null ? '' : ev.price > lastPrice ? 'up' : ev.price < lastPrice ? 'down' : '');
                    lastPrice = ev.price;
                    seq.textContent = 'seq ' + ev.seq;
                } else if (ev.kind === 'chat') {
                    addChat(ev);
                } else if (ev.kind === 'note') {
                    seq.textContent = 'seq ' + ev.seq + ' · "' + ev.text + '"';
                }
                renderStats();
            },
            onState: function (s, detail) {
                dot.className = 'status-dot ' + (s === 'idle' ? '' : s);
                stateText.textContent = s + (detail ? ' — ' + detail : '');
            },
            onWire: function (dir, text, meta) { wire.add(dir, text, meta); renderStats(); }
        };

        var transport = { 'short-polling': Lab.ShortPolling, 'long-polling': Lab.LongPolling, 'sse': Lab.SSE, 'websocket': Lab.WS }[kind](hooks);

        function tile(value, label, cls) {
            var t = Lab.el('div', 'stat-tile' + (cls ? ' ' + cls : ''));
            t.appendChild(Lab.el('div', 'stat-tile__value', value));
            t.appendChild(Lab.el('div', 'stat-tile__label', label));
            return t;
        }
        function renderStats() {
            var s = transport.stats.summary();
            while (statsNode.firstChild) statsNode.removeChild(statsNode.firstChild);
            statsNode.appendChild(tile(s.requests, 'HTTP requests'));
            statsNode.appendChild(tile(s.perMinute, 'requests / min'));
            statsNode.appendChild(tile(s.events, 'events received', 'stat-tile--good'));
            if (kind === 'short-polling' || kind === 'long-polling') statsNode.appendChild(tile(s.wasted + '%', 'wasted requests', s.wasted > 50 ? 'stat-tile--bad' : ''));
            statsNode.appendChild(tile(Lab.bytes(s.bytes), 'bytes (est.)'));
            statsNode.appendChild(tile(s.latency === null ? '—' : s.latency + ' ms', 'avg latency'));
            statsNode.appendChild(tile(s.reconnects, 'reconnects'));
            statsNode.appendChild(tile(s.errors, 'errors', s.errors ? 'stat-tile--bad' : ''));
        }
        renderStats();

        var start = document.getElementById('start'), stop = document.getElementById('stop');
        start.addEventListener('click', function () { transport.stats.reset(); transport.start(); start.disabled = true; stop.disabled = false; });
        stop.addEventListener('click', function () { transport.stop(); start.disabled = false; stop.disabled = true; renderStats(); });
        window.addEventListener('pagehide', function () { transport.stop(); });

        document.getElementById('outage').addEventListener('click', async function () {
            wire.add('sys', 'asked the server to go away for 8 s');
            await Lab.outage(8);
        });
        document.getElementById('publish').addEventListener('click', async function () {
            wire.add('sys', 'POST /lab/api/ticker/publish (a normal request, from this tab)');
            await Lab.publish('hello from ' + kind);
        });
        document.getElementById('pause').addEventListener('change', function (e) { wire.paused = e.target.checked; });
        document.getElementById('clearLog').addEventListener('click', function () { wire.clear(); });

        var interval = document.getElementById('interval');
        if (interval) {
            var out = document.querySelector('output[for="interval"]');
            interval.addEventListener('input', function () { out.textContent = interval.value + ' ms'; transport.setInterval(parseInt(interval.value, 10)); });
        }

        /* chat (websocket page only) */
        var chat = document.getElementById('chat'), chatForm = document.getElementById('chatForm');
        function addChat(ev) {
            if (!chat) return;
            var m = Lab.el('div', 'chat__msg');
            m.appendChild(Lab.el('strong', null, ev.sender + ': '));
            m.appendChild(document.createTextNode(ev.text));
            chat.appendChild(m); chat.scrollTop = chat.scrollHeight;
        }
        if (chatForm) {
            var name = 'tab-' + Math.random().toString(36).slice(2, 6);
            chatForm.addEventListener('submit', function (e) {
                e.preventDefault();
                var input = document.getElementById('chatText');
                if (!input.value.trim()) return;
                if (!transport.send({ type: 'chat', text: input.value, name: name })) {
                    wire.add('err', 'not connected — press Connect first');
                    return;
                }
                input.value = '';
            });
        }
    });
})();
