/* Shared Web Lab widgets: the wire log, stats tiles, and the transports.

   Every transport exposes the same tiny interface —
     start(), stop(), name, and it reports through the same hooks:
     onEvent(event, meta), onState(state), onWire(dir, text, meta) —
   so one page can drive any of them, and the comparison page all four. */
window.Lab = (function () {

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text !== undefined && text !== null) n.textContent = String(text);
        return n;
    }

    function fmtTime(ms) {
        var d = new Date(ms);
        return d.toTimeString().slice(0, 8) + '.' + String(d.getMilliseconds()).padStart(3, '0').slice(0, 2);
    }

    function bytes(n) {
        if (n < 1024) return n + ' B';
        if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
        return (n / 1048576).toFixed(2) + ' MB';
    }

    /* Rough size of a request or response as it would be on the wire:
       payload plus a typical header block. Headers are not readable from JS,
       so this is an estimate, stated as such in the UI. */
    var REQUEST_HEADERS = 420;
    var RESPONSE_HEADERS = 240;

    /* --- wire log -------------------------------------------------------- */
    function WireLog(container, limit) {
        this.node = container;
        this.limit = limit || 300;
        this.paused = false;
    }
    WireLog.prototype.add = function (dir, text, meta) {
        if (this.paused) return;
        var line = el('div', 'wire__line');
        line.appendChild(el('span', 'wire__time', fmtTime(Date.now())));
        line.appendChild(el('span', 'wire__dir ' + dir, { out: '→', in: '←', err: '✕', sys: '·' }[dir] + ' ' + dir.toUpperCase()));
        line.appendChild(el('span', 'wire__text', text));
        line.appendChild(el('span', 'wire__meta', meta || ''));
        var atBottom = this.node.scrollTop + this.node.clientHeight >= this.node.scrollHeight - 8;
        this.node.appendChild(line);
        while (this.node.childNodes.length > this.limit) this.node.removeChild(this.node.firstChild);
        if (atBottom) this.node.scrollTop = this.node.scrollHeight;
    };
    WireLog.prototype.clear = function () { while (this.node.firstChild) this.node.removeChild(this.node.firstChild); };

    /* --- stats ----------------------------------------------------------- */
    function Stats() {
        this.reset();
    }
    Stats.prototype.reset = function () {
        this.requests = 0; this.useful = 0; this.bytes = 0; this.events = 0;
        this.latencies = []; this.reconnects = 0; this.errors = 0; this.startedAt = Date.now();
    };
    Stats.prototype.latency = function (serverMs) {
        var l = Date.now() - serverMs;
        if (l >= 0 && l < 60000) { this.latencies.push(l); if (this.latencies.length > 50) this.latencies.shift(); }
        return l;
    };
    Stats.prototype.avgLatency = function () {
        if (!this.latencies.length) return null;
        return Math.round(this.latencies.reduce(function (a, b) { return a + b; }, 0) / this.latencies.length);
    };
    Stats.prototype.summary = function () {
        var secs = Math.max(1, (Date.now() - this.startedAt) / 1000);
        return {
            requests: this.requests,
            useful: this.useful,
            wasted: this.requests ? Math.round((1 - this.useful / this.requests) * 100) : 0,
            bytes: this.bytes,
            perMinute: Math.round(this.requests / secs * 60),
            events: this.events,
            latency: this.avgLatency(),
            reconnects: this.reconnects,
            errors: this.errors
        };
    };

    /* --- transports ------------------------------------------------------ */

    function base(name, hooks) {
        return {
            name: name,
            stats: new Stats(),
            hooks: hooks,
            running: false,
            emit: function (event) {
                this.stats.events += 1;
                var lat = event.server_ms ? this.stats.latency(event.server_ms) : null;
                hooks.onEvent && hooks.onEvent(event, { latency: lat, transport: name });
            },
            state: function (s, detail) { hooks.onState && hooks.onState(s, detail, name); },
            wire: function (dir, text, meta) { hooks.onWire && hooks.onWire(dir, text, meta, name); }
        };
    }

    /* 1. Short polling */
    function ShortPolling(hooks, intervalMs) {
        var t = base('polling', hooks);
        var timer = null, since = null, inflight = false;
        t.interval = intervalMs || 1000;

        async function tick() {
            if (!t.running || inflight) return;
            inflight = true;
            var url = '/lab/api/ticker/poll' + (since !== null ? '?since=' + since : '');
            t.wire('out', 'GET ' + url, '~' + REQUEST_HEADERS + ' B');
            t.stats.requests += 1; t.stats.bytes += REQUEST_HEADERS;
            try {
                var r = await fetch(url, { cache: 'no-store' });
                var text = await r.text();
                t.stats.bytes += RESPONSE_HEADERS + text.length;
                if (r.status === 503) {
                    t.stats.errors += 1; t.state('off', '503 outage');
                    t.wire('err', '503 Service Unavailable', 'Retry-After ' + r.headers.get('Retry-After') + 's');
                } else {
                    var data = JSON.parse(text);
                    since = data.seq;
                    if (data.changed) { t.stats.useful += 1; t.emit(data.event); }
                    t.wire('in', (data.changed ? 'new data  ' : 'unchanged ') + 'seq ' + data.seq, text.length + ' B');
                    t.state('on');
                }
            } catch (e) {
                t.stats.errors += 1; t.state('off', 'network error'); t.wire('err', String(e.message || e));
            } finally { inflight = false; }
        }
        t.start = function () { if (t.running) return; t.running = true; t.state('on'); tick(); timer = setInterval(tick, t.interval); };
        t.stop = function () { t.running = false; clearInterval(timer); t.state('idle'); };
        t.setInterval = function (ms) { t.interval = ms; if (t.running) { clearInterval(timer); timer = setInterval(tick, ms); } };
        return t;
    }

    /* 2. Long polling */
    function LongPolling(hooks) {
        var t = base('long-polling', hooks);
        var since = 0, controller = null, backoff = 500;

        async function loop() {
            while (t.running) {
                var url = '/lab/api/ticker/long?since=' + since;
                controller = new AbortController();
                t.wire('out', 'GET ' + url + '   (server holds it open…)', '~' + REQUEST_HEADERS + ' B');
                t.stats.requests += 1; t.stats.bytes += REQUEST_HEADERS;
                var started = Date.now();
                try {
                    var r = await fetch(url, { signal: controller.signal, cache: 'no-store' });
                    var text = await r.text();
                    t.stats.bytes += RESPONSE_HEADERS + text.length;
                    var held = ((Date.now() - started) / 1000).toFixed(1) + 's';
                    if (r.status === 503) {
                        t.stats.errors += 1; t.state('off', '503 outage');
                        t.wire('err', '503 Service Unavailable — retrying in ' + backoff + 'ms', 'held ' + held);
                        await sleep(backoff); backoff = Math.min(backoff * 2, 8000); t.stats.reconnects += 1;
                        continue;
                    }
                    backoff = 500;
                    var data = JSON.parse(text);
                    since = data.seq;
                    if (data.changed) {
                        t.stats.useful += 1;
                        data.events.forEach(function (ev) { t.emit(ev); });
                        t.wire('in', data.events.length + ' event(s) up to seq ' + data.seq, 'held ' + held + ' · ' + text.length + ' B');
                    } else {
                        t.wire('in', 'timeout, nothing new — asking again', 'held ' + held);
                    }
                    t.state('on');
                } catch (e) {
                    if (!t.running) break;
                    t.stats.errors += 1; t.state('off', 'network error'); t.wire('err', String(e.message || e));
                    await sleep(backoff); backoff = Math.min(backoff * 2, 8000); t.stats.reconnects += 1;
                }
            }
        }
        t.start = function () { if (t.running) return; t.running = true; t.state('wait', 'waiting'); loop(); };
        t.stop = function () { t.running = false; if (controller) controller.abort(); t.state('idle'); };
        return t;
    }

    /* 3. Server-Sent Events */
    function SSE(hooks) {
        var t = base('sse', hooks);
        var source = null, opened = false;
        t.start = function () {
            if (t.running) return;
            t.running = true; opened = false;
            t.wire('out', 'GET /lab/api/ticker/sse   Accept: text/event-stream', '~' + REQUEST_HEADERS + ' B (once)');
            t.stats.requests += 1; t.stats.bytes += REQUEST_HEADERS + RESPONSE_HEADERS;
            source = new EventSource('/lab/api/ticker/sse');
            source.onopen = function () {
                if (opened) { t.stats.reconnects += 1; t.wire('sys', 'reconnected — browser sent Last-Event-ID automatically'); }
                opened = true; t.state('on');
            };
            var handle = function (e) {
                var data = JSON.parse(e.data);
                t.stats.useful += 1; t.stats.bytes += e.data.length + 30;
                t.emit(data);
                t.wire('in', 'event: ' + e.type + '  id: ' + e.lastEventId, (e.data.length + 30) + ' B');
            };
            source.addEventListener('tick', handle);
            source.addEventListener('chat', handle);
            source.addEventListener('note', handle);
            source.addEventListener('outage', function () { t.wire('err', 'server announced outage; stream closing'); });
            source.onerror = function () {
                t.stats.errors += 1;
                t.state(source.readyState === EventSource.CLOSED ? 'off' : 'wait', 'reconnecting');
                t.wire('err', 'connection lost — EventSource retries by itself');
            };
        };
        t.stop = function () { t.running = false; if (source) source.close(); t.state('idle'); };
        return t;
    }

    /* 4. WebSocket */
    function WS(hooks) {
        var t = base('websocket', hooks);
        var socket = null, backoff = 500, pingTimer = null, wasOpen = false;
        function url() { return (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/lab/api/ticker/ws'; }
        function connect() {
            t.wire('out', 'GET /lab/api/ticker/ws   Upgrade: websocket', 'handshake ~' + REQUEST_HEADERS + ' B');
            t.stats.requests += 1; t.stats.bytes += REQUEST_HEADERS + RESPONSE_HEADERS;
            socket = new WebSocket(url());
            socket.onopen = function () {
                if (wasOpen) t.stats.reconnects += 1;
                wasOpen = true; backoff = 500; t.state('on');
                t.wire('sys', 'socket open — frames from here on carry ~6 B of overhead each');
                pingTimer = setInterval(function () { t.send({ type: 'ping', client_ms: Date.now() }); }, 5000);
            };
            socket.onmessage = function (e) {
                var data = JSON.parse(e.data);
                t.stats.bytes += e.data.length + 6;
                if (data.kind === 'pong') {
                    var rtt = Date.now() - data.client_ms;
                    t.stats.latency(Date.now() - Math.round(rtt / 2));      // one-way estimate
                    t.wire('in', 'pong  round-trip ' + rtt + ' ms', (e.data.length + 6) + ' B');
                    hooks.onRtt && hooks.onRtt(rtt);
                    return;
                }
                t.stats.useful += 1;
                t.emit(data);
                t.wire('in', data.kind + (data.seq ? '  seq ' + data.seq : ''), (e.data.length + 6) + ' B');
            };
            socket.onclose = function (e) {
                clearInterval(pingTimer);
                if (!t.running) return;
                t.stats.errors += 1; t.state('off', 'closed ' + e.code);
                t.wire('err', 'closed (code ' + e.code + (e.reason ? ', ' + e.reason : '') + ') — reconnecting in ' + backoff + 'ms');
                setTimeout(function () { if (t.running) connect(); }, backoff);
                backoff = Math.min(backoff * 2, 8000);
            };
            socket.onerror = function () { /* onclose follows */ };
        }
        t.send = function (obj) {
            if (!socket || socket.readyState !== WebSocket.OPEN) return false;
            var text = JSON.stringify(obj);
            socket.send(text);
            t.stats.bytes += text.length + 6;
            if (obj.type !== 'ping') t.wire('out', 'send ' + text, (text.length + 6) + ' B');
            return true;
        };
        t.start = function () { if (t.running) return; t.running = true; wasOpen = false; connect(); };
        t.stop = function () { t.running = false; clearInterval(pingTimer); if (socket) socket.close(1000, 'stopped'); t.state('idle'); };
        return t;
    }

    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

    async function outage(seconds) {
        var r = await fetch('/lab/api/ticker/outage', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ seconds: seconds }) });
        return r.json();
    }
    async function publish(text) {
        var r = await fetch('/lab/api/ticker/publish', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text }) });
        return r.json();
    }

    return { el: el, bytes: bytes, WireLog: WireLog, Stats: Stats,
             ShortPolling: ShortPolling, LongPolling: LongPolling, SSE: SSE, WS: WS,
             outage: outage, publish: publish };
})();
