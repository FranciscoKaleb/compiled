/* Level 5 — browser platform. One section per page, picked by LAB_PAGE. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var page = window.LAB_PAGE;
        var wire = new Lab.WireLog(document.getElementById('wire'));
        document.getElementById('pause').addEventListener('change', function (e) { wire.paused = e.target.checked; });
        document.getElementById('clearLog').addEventListener('click', function () { wire.clear(); });
        function tile(v, l, c) { var t = Lab.el('div', 'stat-tile' + (c ? ' ' + c : '')); t.appendChild(Lab.el('div', 'stat-tile__value', v)); t.appendChild(Lab.el('div', 'stat-tile__label', l)); return t; }
        function setTiles(node, tiles) { while (node.firstChild) node.removeChild(node.firstChild); tiles.forEach(function (t) { node.appendChild(tile(t[0], t[1], t[2])); }); }
        function clear(n) { while (n && n.firstChild) n.removeChild(n.firstChild); }
        function bindRange(id, fmt) { var r = document.getElementById(id), o = document.querySelector('output[for="' + id + '"]'); var f = function () { o.textContent = fmt(parseInt(r.value, 10)); }; f(); r.addEventListener('input', f); return r; }

        /* ================================================================ */
        if (page === 'web-workers') {
            var clicks = 0, pulseDir = 1, pulse = 0;
            setInterval(function () {
                document.getElementById('clock').textContent = new Date().toTimeString().slice(0, 8) + '.' + String(Math.floor(Date.now() % 1000 / 100));
                pulse += 5 * pulseDir; if (pulse >= 100 || pulse <= 0) pulseDir *= -1;
                document.getElementById('pulse').style.width = pulse + '%';
            }, 100);
            document.getElementById('clickMe').addEventListener('click', function () { clicks += 1; document.getElementById('clicks').textContent = clicks + ' clicks registered'; });
            var nIn = bindRange('n', function (v) { return v + ' M'; });
            var stats = {}, statsNode = document.getElementById('stats');
            function render() { setTiles(statsNode, [[stats.mainMs === undefined ? '—' : stats.mainMs + ' ms', 'main thread', 'stat-tile--bad'], [stats.workerMs === undefined ? '—' : stats.workerMs + ' ms', 'worker', 'stat-tile--good'], [stats.frozen === undefined ? '—' : stats.frozen + ' ms', 'longest UI freeze']]); }
            render();
            function heavy(n) { var acc = 0; for (var i = 1; i <= n; i++) acc += Math.sin(i) * Math.cos(i / 3) / (1 + (i % 7)); return acc; }
            // Measure UI freezes: a 50 ms timer that reports how late it actually fired.
            var last = performance.now(), worst = 0;
            setInterval(function () { var now = performance.now(); var late = now - last - 50; if (late > worst) { worst = late; stats.frozen = Math.round(worst); render(); } last = now; }, 50);

            document.getElementById('runMain').addEventListener('click', function () {
                var n = parseInt(nIn.value, 10) * 1e6; worst = 0;
                wire.add('sys', 'main thread: starting ' + n / 1e6 + ' M iterations — the page is about to stop responding');
                document.getElementById('progress').style.width = '0%';
                setTimeout(function () {                                     // let the log line paint first
                    var t0 = performance.now(); var r = heavy(n); stats.mainMs = Math.round(performance.now() - t0);
                    document.getElementById('progress').style.width = '100%';
                    wire.add('in', 'main thread: done, result ' + r.toFixed(3), stats.mainMs + ' ms — nothing painted in between'); render();
                }, 30);
            });
            document.getElementById('runWorker').addEventListener('click', function () {
                var n = parseInt(nIn.value, 10) * 1e6; worst = 0;
                var worker = new Worker('/static/js/lab_worker.js');
                wire.add('out', 'postMessage({n: ' + n + '}) → worker  (structured clone, separate thread)');
                worker.onmessage = function (e) {
                    if (e.data.progress !== undefined) { document.getElementById('progress').style.width = (e.data.progress * 100) + '%'; return; }
                    stats.workerMs = e.data.ms; wire.add('in', 'worker: done, result ' + e.data.result.toFixed(3), e.data.ms + ' ms — the clock never stopped'); render(); worker.terminate();
                };
                worker.onerror = function (e) { wire.add('err', 'worker error: ' + e.message); };
            });
        }

        /* ================================================================ */
        if (page === 'offline') {
            var swDot = document.getElementById('swDot'), swState = document.getElementById('swState');
            function online() { var n = document.getElementById('online'); n.textContent = navigator.onLine ? 'You are online.' : 'You are OFFLINE. Everything you see now came from the service worker\'s cache.'; n.className = 'alert ' + (navigator.onLine ? 'alert--warn' : 'alert--error'); }
            window.addEventListener('online', online); window.addEventListener('offline', online); online();
            if (!('serviceWorker' in navigator)) { swState.textContent = 'not supported here'; return; }
            navigator.serviceWorker.addEventListener('message', function (e) {
                var d = e.data; if (d.from !== 'sw') return;
                wire.add(d.source.indexOf('FAILED') === 0 ? 'err' : 'sys', 'SW ' + d.strategy + ': ' + d.source + (d.url ? '  ' + d.url : ''));
            });
            async function status() {
                var reg = await navigator.serviceWorker.getRegistration('/lab/offline');
                if (reg && reg.active) { swDot.className = 'status-dot on'; swState.textContent = 'active, scope ' + new URL(reg.scope).pathname + (navigator.serviceWorker.controller ? ' — controlling this page' : ' — reload to be controlled'); }
                else if (reg) { swDot.className = 'status-dot wait'; swState.textContent = 'installing…'; }
                else { swDot.className = 'status-dot'; swState.textContent = 'not installed'; }
            }
            status();
            document.getElementById('install').addEventListener('click', async function () {
                wire.add('out', "navigator.serviceWorker.register('/lab/sw.js', {scope: '/lab/offline'})");
                try {
                    var reg = await navigator.serviceWorker.register('/lab/sw.js', { scope: '/lab/offline' });
                    wire.add('in', 'registered. Installing: precaching the app shell (this page + its CSS/JS)…');
                    await navigator.serviceWorker.ready; await status();
                    wire.add('sys', 'active. Reload once so this page is controlled by the worker, then go offline and reload again.');
                } catch (e) { wire.add('err', e.message); }
            });
            document.getElementById('uninstall').addEventListener('click', async function () {
                var reg = await navigator.serviceWorker.getRegistration('/lab/offline');
                if (reg) await reg.unregister();
                var keys = await caches.keys(); for (var k of keys) if (k.indexOf('lab-offline') === 0) await caches.delete(k);
                wire.add('sys', 'unregistered and cache cleared. Reload to detach.'); status();
            });
            document.querySelectorAll('[data-strategy]').forEach(function (b) {
                b.addEventListener('click', async function () {
                    var s = b.dataset.strategy, url = '/lab/api/browser/offline/time?strategy=' + s;
                    wire.add('out', 'fetch(' + url + ')' + (navigator.serviceWorker.controller ? '   → intercepted by the service worker' : '   (no worker controlling this page: goes straight to the network)'));
                    var t0 = performance.now();
                    try {
                        var r = await fetch(url); var d = await r.json(); var ms = Math.round(performance.now() - t0);
                        if (d.offline) { wire.add('err', '503 offline fallback response', ms + ' ms'); document.getElementById('serverTime').textContent = 'offline'; return; }
                        var age = Math.round((Date.now() - d.fetched_at_ms) / 1000);
                        document.getElementById('serverTime').textContent = d.server_time;
                        document.getElementById('fetchMeta').textContent = ms + ' ms · answer is ' + age + ' s old';
                        wire.add('in', 'server_time ' + d.server_time + (age > 2 ? '   ← stale by ' + age + ' s: this came from the cache' : '   fresh'), ms + ' ms');
                    } catch (e) { wire.add('err', 'fetch failed: ' + e.message + ' (offline with no worker or nothing cached)'); }
                });
            });
        }

        /* ================================================================ */
        if (page === 'webrtc') {
            var pc = null, ws = null, local = null, role = null, statsTimer = null, signalBytes = 0, canvasTimer = null;
            var stats = { media: 0, signal: 0, candidates: 0, path: '—' }, statsNode = document.getElementById('stats');
            function render() { setTiles(statsNode, [[Lab.bytes(stats.signal), 'signalling bytes via server'], [Lab.bytes(stats.media), 'media bytes peer-to-peer', 'stat-tile--good'], [stats.candidates, 'ICE candidates'], [stats.path, 'connection path']]); }
            render();
            function synthetic() {
                var c = document.createElement('canvas'); c.width = 320; c.height = 240; var ctx = c.getContext('2d'); var t = 0;
                var hue = Math.floor(Math.random() * 360);
                canvasTimer = setInterval(function () {
                    t += 1; ctx.fillStyle = 'hsl(' + hue + ',40%,15%)'; ctx.fillRect(0, 0, 320, 240);
                    ctx.fillStyle = 'hsl(' + hue + ',80%,60%)'; ctx.beginPath(); ctx.arc(160 + Math.sin(t / 20) * 100, 120 + Math.cos(t / 15) * 60, 30, 0, 7); ctx.fill();
                    ctx.fillStyle = '#fff'; ctx.font = '20px system-ui'; ctx.fillText((role || '?') + ' · ' + new Date().toTimeString().slice(0, 8), 12, 30);
                }, 40);
                return c.captureStream(25);
            }
            function send(obj) { var s = JSON.stringify(obj); stats.signal += s.length; ws.send(s); wire.add('out', 'signal → server → peer: ' + obj.type + (obj.type === 'candidate' ? '  ' + (obj.candidate.candidate || '').split(' ').slice(4, 8).join(' ') : ''), s.length + ' B'); render(); }
            async function start() {
                var room = document.getElementById('room').value.trim() || 'lab-demo';
                try { local = document.getElementById('synthetic').checked ? synthetic() : await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240 }, audio: false }); }
                catch (e) { wire.add('err', 'camera: ' + e.message); return; }
                document.getElementById('local').srcObject = local; document.getElementById('localState').textContent = 'capturing';
                pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] });
                local.getTracks().forEach(function (t) { pc.addTrack(t, local); });
                pc.onicecandidate = function (e) { if (e.candidate) { stats.candidates += 1; send({ type: 'candidate', candidate: e.candidate.toJSON() }); } };
                pc.ontrack = function (e) { document.getElementById('remote').srcObject = e.streams[0]; document.getElementById('remoteState').textContent = 'receiving'; wire.add('in', 'remote track arrived — this is peer-to-peer media, not via the server'); };
                pc.onconnectionstatechange = function () { wire.add('sys', 'connectionState: ' + pc.connectionState); document.getElementById('remoteState').textContent = pc.connectionState; if (pc.connectionState === 'connected') startStats(); };
                var url = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/lab/api/browser/rtc/ws?room=' + encodeURIComponent(room);
                ws = new WebSocket(url);
                wire.add('out', 'signalling: open ' + url);
                ws.onmessage = async function (e) {
                    var m = JSON.parse(e.data); stats.signal += e.data.length; render();
                    if (m.type === 'role') { role = m.role; wire.add('in', 'you are the ' + role + ' (' + m.peers + ' in room)'); if (m.peers === 1) wire.add('sys', 'waiting for a second tab to join "' + room + '"…'); return; }
                    if (m.type === 'full') { wire.add('err', m.message); stop(); return; }
                    if (m.type === 'peer-joined') { wire.add('in', 'peer joined'); if (role === 'caller') { var offer = await pc.createOffer(); await pc.setLocalDescription(offer); send({ type: 'offer', sdp: offer.sdp }); } return; }
                    if (m.type === 'offer') { wire.add('in', 'offer received (' + m.sdp.length + ' B of SDP)'); await pc.setRemoteDescription({ type: 'offer', sdp: m.sdp }); var ans = await pc.createAnswer(); await pc.setLocalDescription(ans); send({ type: 'answer', sdp: ans.sdp }); return; }
                    if (m.type === 'answer') { wire.add('in', 'answer received'); await pc.setRemoteDescription({ type: 'answer', sdp: m.sdp }); return; }
                    if (m.type === 'candidate') { stats.candidates += 1; wire.add('in', 'candidate from peer'); try { await pc.addIceCandidate(m.candidate); } catch (err) {} render(); return; }
                    if (m.type === 'peer-left') { wire.add('err', 'peer left'); document.getElementById('remote').srcObject = null; document.getElementById('remoteState').textContent = 'gone'; }
                };
                ws.onclose = function () { wire.add('sys', 'signalling socket closed — the media keeps flowing if already connected'); };
                document.getElementById('join').disabled = true; document.getElementById('leave').disabled = false;
            }
            function startStats() {
                statsTimer = setInterval(async function () {
                    if (!pc) return;
                    var report = await pc.getStats(); var bytes = 0, pair = null;
                    report.forEach(function (s) {
                        if (s.type === 'inbound-rtp' || s.type === 'outbound-rtp') bytes += (s.bytesReceived || 0) + (s.bytesSent || 0);
                        if (s.type === 'candidate-pair' && s.state === 'succeeded' && s.nominated) pair = s;
                    });
                    stats.media = bytes;
                    if (pair) { var l = report.get(pair.localCandidateId), r = report.get(pair.remoteCandidateId); stats.path = (l ? l.candidateType : '?') + ' ↔ ' + (r ? r.candidateType : '?'); }
                    render();
                }, 1000);
            }
            function stop() {
                if (statsTimer) clearInterval(statsTimer); if (canvasTimer) clearInterval(canvasTimer);
                if (pc) pc.close(); if (ws) ws.close(); if (local) local.getTracks().forEach(function (t) { t.stop(); });
                pc = ws = local = null; document.getElementById('local').srcObject = null; document.getElementById('remote').srcObject = null;
                document.getElementById('join').disabled = false; document.getElementById('leave').disabled = true;
                document.getElementById('localState').textContent = '—'; document.getElementById('remoteState').textContent = '—';
            }
            document.getElementById('join').addEventListener('click', start);
            document.getElementById('leave').addEventListener('click', function () { stop(); wire.add('sys', 'left the room'); });
            window.addEventListener('pagehide', stop);
        }

        /* ================================================================ */
        if (page === 'wasm') {
            var sizeIn = bindRange('size', function (v) { return v + ' × ' + Math.round(v * 2 / 3); }), itersIn = bindRange('iters', function (v) { return String(v); });
            var instance = null, best = { js: null, wasm: null }, statsNode = document.getElementById('stats');
            function mandelJS(out, w, h, maxIter) {
                for (var y = 0; y < h; y++) for (var x = 0; x < w; x++) {
                    var cr = x / w * 3.5 - 2.5, ci = y / h * 2.0 - 1.0, zr = 0, zi = 0, i = 0;
                    while (i < maxIter && zr * zr + zi * zi <= 4.0) { var t = zr * zr - zi * zi + cr; zi = 2 * zr * zi + ci; zr = t; i++; }
                    out[y * w + x] = Math.trunc(i * 255 / maxIter);
                }
            }
            document.getElementById('jsSource').textContent = mandelJS.toString();
            function paint(canvas, data, w, h) {
                canvas.width = w; canvas.height = h; var ctx = canvas.getContext('2d'); var img = ctx.createImageData(w, h);
                for (var k = 0; k < w * h; k++) { var v = data[k]; var o = k * 4; if (v === 255) { img.data[o] = img.data[o + 1] = img.data[o + 2] = 0; } else { img.data[o] = v * 2 % 256; img.data[o + 1] = (v * 5) % 256; img.data[o + 2] = 120 + v / 2; } img.data[o + 3] = 255; }
                ctx.putImageData(img, 0, 0);
            }
            function render() { setTiles(statsNode, [[best.js === null ? '—' : best.js + ' ms', 'JavaScript (best)'], [best.wasm === null ? '—' : best.wasm + ' ms', 'WebAssembly (best)', 'stat-tile--good'], [(best.js && best.wasm) ? (best.js / best.wasm).toFixed(2) + '×' : '—', 'speed-up']]); }
            render();
            async function load() {
                if (instance) return instance;
                wire.add('out', 'fetch /static/wasm/mandel.wasm → WebAssembly.instantiate');
                var t0 = performance.now(); var res = await fetch('/static/wasm/mandel.wasm'); var bytes = await res.arrayBuffer();
                var result = await WebAssembly.instantiate(bytes); instance = result.instance;
                wire.add('in', 'module compiled: exports ' + Object.keys(instance.exports).join(', ') + ' · ' + bytes.byteLength + ' bytes', Math.round(performance.now() - t0) + ' ms');
                return instance;
            }
            async function runJs() {
                var w = parseInt(sizeIn.value, 10), h = Math.round(w * 2 / 3), it = parseInt(itersIn.value, 10);
                var out = new Uint8Array(w * h); var t0 = performance.now(); mandelJS(out, w, h, it); var ms = Math.round(performance.now() - t0);
                paint(document.getElementById('jsCanvas'), out, w, h); document.getElementById('jsMs').textContent = ms + ' ms';
                if (best.js === null || ms < best.js) best.js = ms; wire.add('in', 'JavaScript: ' + w + '×' + h + ' @ ' + it, ms + ' ms'); render();
            }
            async function runWasm() {
                var inst = await load(); var w = parseInt(sizeIn.value, 10), h = Math.round(w * 2 / 3), it = parseInt(itersIn.value, 10);
                var need = w * h, have = inst.exports.memory.buffer.byteLength;
                if (need > have) { inst.exports.memory.grow(Math.ceil((need - have) / 65536)); wire.add('sys', 'memory.grow → ' + Lab.bytes(inst.exports.memory.buffer.byteLength)); }
                var t0 = performance.now(); inst.exports.mandel(w, h, it); var ms = Math.round(performance.now() - t0);
                var view = new Uint8Array(inst.exports.memory.buffer, 0, w * h);
                paint(document.getElementById('wasmCanvas'), view, w, h); document.getElementById('wasmMs').textContent = ms + ' ms';
                if (best.wasm === null || ms < best.wasm) best.wasm = ms; wire.add('in', 'WebAssembly: ' + w + '×' + h + ' @ ' + it + ' (read straight from linear memory)', ms + ' ms'); render();
            }
            document.getElementById('runJs').addEventListener('click', runJs);
            document.getElementById('runWasm').addEventListener('click', runWasm);
            document.getElementById('runBoth').addEventListener('click', async function () { for (var i = 0; i < 3; i++) { await runJs(); await new Promise(function (r) { setTimeout(r, 30); }); await runWasm(); await new Promise(function (r) { setTimeout(r, 30); }); } });
        }

        /* ================================================================ */
        if (page === 'push') {
            var dot = document.getElementById('pushDot'), state = document.getElementById('pushState'), info = document.getElementById('subInfo');
            function urlB64ToUint8(b64) { var pad = '='.repeat((4 - b64.length % 4) % 4); var raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/')); var arr = new Uint8Array(raw.length); for (var i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i); return arr; }
            if (!('serviceWorker' in navigator) || !('PushManager' in window)) { state.textContent = 'push is not supported in this browser'; return; }
            async function reg() { return navigator.serviceWorker.register('/lab/sw.js', { scope: '/lab/push' }); }
            async function status() {
                var r = await navigator.serviceWorker.getRegistration('/lab/push'); var sub = r ? await r.pushManager.getSubscription() : null;
                var perm = Notification.permission;
                if (sub) { dot.className = 'status-dot on'; state.textContent = 'subscribed · permission ' + perm; info.textContent = JSON.stringify(sub.toJSON(), null, 2); document.getElementById('unsubscribe').disabled = false; document.getElementById('subscribe').disabled = true; }
                else { dot.className = 'status-dot ' + (perm === 'denied' ? 'off' : ''); state.textContent = 'not subscribed · permission ' + perm; info.textContent = '—'; document.getElementById('unsubscribe').disabled = true; document.getElementById('subscribe').disabled = perm === 'denied'; }
                return sub;
            }
            status();
            document.getElementById('subscribe').addEventListener('click', async function () {
                try {
                    wire.add('out', 'GET /lab/api/browser/push/key'); var k = await (await fetch('/lab/api/browser/push/key')).json();
                    if (!k.ok) { wire.add('err', k.error); return; }
                    wire.add('in', 'VAPID public key ' + k.public_key.slice(0, 16) + '…');
                    var r = await reg(); await navigator.serviceWorker.ready;
                    wire.add('out', 'pushManager.subscribe({userVisibleOnly: true, applicationServerKey})   → the browser asks its push service');
                    var sub = await r.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlB64ToUint8(k.public_key) });
                    var j = sub.toJSON(); wire.add('in', 'endpoint at ' + new URL(j.endpoint).host + ' · keys p256dh + auth');
                    wire.add('out', 'POST /lab/api/browser/push/subscribe {endpoint, keys}');
                    var res = await (await fetch('/lab/api/browser/push/subscribe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(j) })).json();
                    wire.add('in', res.note); status();
                } catch (e) { wire.add('err', e.name + ': ' + e.message + (Notification.permission === 'denied' ? ' — notifications are blocked for this site; allow them in the address-bar site settings' : '')); status(); }
            });
            document.getElementById('unsubscribe').addEventListener('click', async function () {
                var sub = await status(); if (!sub) return;
                await fetch('/lab/api/browser/push/unsubscribe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(sub.toJSON()) });
                await sub.unsubscribe(); wire.add('sys', 'unsubscribed on both sides'); status();
            });
            async function send() {
                var body = { title: document.getElementById('title').value, body: document.getElementById('body').value };
                wire.add('out', 'POST /lab/api/browser/push/send ' + JSON.stringify(body));
                var res = await (await fetch('/lab/api/browser/push/send', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json();
                var out = document.getElementById('sendResult'); clear(out);
                if (!res.ok) { wire.add('err', res.error); out.appendChild(UI.alert('error', res.error)); return; }
                res.results.forEach(function (r) { wire.add(r.error ? 'err' : 'in', 'push service ' + r.push_service + ' → HTTP ' + r.status + (r.error ? ' ' + r.error : ' accepted; it will wake the browser'), r.ms + ' ms'); });
                out.appendChild(UI.alert(res.results.every(function (r) { return !r.error; }) ? 'success' : 'error', res.sent + ' push(es) sent. Status ' + res.results.map(function (r) { return r.status; }).join(', ') + '. Watch for the notification.'));
            }
            document.getElementById('send').addEventListener('click', send);
            document.getElementById('sendLater').addEventListener('click', async function () {
                var body = { title: document.getElementById('title').value, body: document.getElementById('body').value, delay: 8 };
                wire.add('out', 'POST /lab/api/browser/push/send {…, delay: 8}   → the SERVER waits, so closing this tab changes nothing');
                var res = await (await fetch('/lab/api/browser/push/send', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json();
                var out = document.getElementById('sendResult'); clear(out);
                if (!res.ok) { wire.add('err', res.error); out.appendChild(UI.alert('error', res.error)); return; }
                wire.add('in', res.note); out.appendChild(UI.alert('warn', res.note + ' Close the tab now, or switch away, and wait for the notification.'));
            });
        }
    });
})();
