/* All four transports at once, one card each. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var grid = document.getElementById('compare');
        var cards = {};
        var transports = [];

        function card(name, title) {
            var c = Lab.el('div', 'compare__card');
            var head = Lab.el('div', 'card__title');
            var dot = Lab.el('span', 'status-dot');
            var h = Lab.el('h3', null, ''); h.style.margin = 0; h.appendChild(dot); h.appendChild(document.createTextNode(title));
            head.appendChild(h);
            var state = Lab.el('span', 'small muted', 'idle');
            head.appendChild(state);
            c.appendChild(head);
            var price = Lab.el('div', 'compare__price', '—'); c.appendChild(price);
            var rows = {};
            ['events', 'requests', 'requests / min', 'wasted', 'bytes (est.)', 'avg latency', 'reconnects', 'errors'].forEach(function (label) {
                var r = Lab.el('div', 'compare__row');
                r.appendChild(Lab.el('span', null, label));
                var v = Lab.el('span', null, '—'); r.appendChild(v);
                rows[label] = v; c.appendChild(r);
            });
            grid.appendChild(c);
            return { dot: dot, state: state, price: price, rows: rows, lastPrice: null };
        }

        function hooksFor(name) {
            return {
                onEvent: function (ev) {
                    var c = cards[name];
                    if (ev.kind === 'tick') {
                        c.price.textContent = ev.price.toFixed(2);
                        c.price.style.color = c.lastPrice === null ? '' : ev.price >= c.lastPrice ? 'var(--brand-strong)' : 'var(--danger)';
                        c.lastPrice = ev.price;
                    }
                },
                onState: function (s, detail) {
                    var c = cards[name];
                    c.dot.className = 'status-dot ' + (s === 'idle' ? '' : s);
                    c.state.textContent = s + (detail ? ' — ' + detail : '');
                },
                onWire: function () {}
            };
        }

        [['polling', 'Short polling', Lab.ShortPolling], ['long-polling', 'Long polling', Lab.LongPolling],
         ['sse', 'Server-Sent Events', Lab.SSE], ['websocket', 'WebSocket', Lab.WS]].forEach(function (def) {
            cards[def[0]] = card(def[0], def[1]);
            transports.push(def[2](hooksFor(def[0])));
        });

        function render() {
            transports.forEach(function (t) {
                var s = t.stats.summary(), r = cards[t.name].rows;
                r['events'].textContent = s.events;
                r['requests'].textContent = s.requests;
                r['requests / min'].textContent = s.perMinute;
                r['wasted'].textContent = (t.name === 'polling' || t.name === 'long-polling') ? s.wasted + '%' : 'n/a';
                r['bytes (est.)'].textContent = Lab.bytes(s.bytes);
                r['avg latency'].textContent = s.latency === null ? '—' : s.latency + ' ms';
                r['reconnects'].textContent = s.reconnects;
                r['errors'].textContent = s.errors;
                r['errors'].style.color = s.errors ? 'var(--danger)' : '';
            });
        }
        setInterval(render, 500);

        var startAll = document.getElementById('startAll'), stopAll = document.getElementById('stopAll');
        var outage = document.getElementById('outage'), publish = document.getElementById('publish');
        startAll.addEventListener('click', function () {
            transports.forEach(function (t) { t.stats.reset(); t.start(); });
            startAll.disabled = true; stopAll.disabled = false; outage.disabled = false; publish.disabled = false;
        });
        stopAll.addEventListener('click', function () {
            transports.forEach(function (t) { t.stop(); });
            startAll.disabled = false; stopAll.disabled = true; outage.disabled = true; publish.disabled = true;
        });
        outage.addEventListener('click', function () { Lab.outage(8); });
        publish.addEventListener('click', function () { Lab.publish('manual event'); });
        document.getElementById('reset').addEventListener('click', function () { transports.forEach(function (t) { t.stats.reset(); }); render(); });
        window.addEventListener('pagehide', function () { transports.forEach(function (t) { t.stop(); }); });
    });
})();
