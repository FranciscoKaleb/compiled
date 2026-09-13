/* Level 4 — auth & sessions. One section per page, picked by LAB_PAGE. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var page = window.LAB_PAGE;
        var wire = new Lab.WireLog(document.getElementById('wire'));
        document.getElementById('pause').addEventListener('change', function (e) { wire.paused = e.target.checked; });
        document.getElementById('clearLog').addEventListener('click', function () { wire.clear(); });
        function clear(n) { while (n && n.firstChild) n.removeChild(n.firstChild); }
        async function api(url, init) {
            init = init || {};
            if (init.body && typeof init.body !== 'string') { init.body = JSON.stringify(init.body); init.headers = Object.assign({ 'Content-Type': 'application/json' }, init.headers || {}); }
            var r = await fetch(url, Object.assign({ cache: 'no-store' }, init));
            var d = await r.json().catch(function () { return {}; });
            return { r: r, d: d };
        }
        function b64url(obj) { return btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); }
        function unb64url(s) { s = s.replace(/-/g, '+').replace(/_/g, '/'); while (s.length % 4) s += '='; return JSON.parse(atob(s)); }

        /* ================================================================ */
        if (page === 'sessions-vs-jwt') {
            var token = null, jwtExp = null, cookieExp = null;
            var ttlIn = document.getElementById('ttl');
            ttlIn.addEventListener('input', function () { document.querySelector('output[for="ttl"]').textContent = ttlIn.value + ' s'; });

            function showParts(t) {
                var box = document.getElementById('jwtParts'); clear(box);
                if (!t) { box.appendChild(Lab.el('p', 'small muted', 'No token.')); return; }
                var parts = t.split('.');
                [['Header', parts[0], 'var(--danger)'], ['Payload (claims)', parts[1], 'var(--accent)'], ['Signature', parts[2], 'var(--brand-strong)']].forEach(function (p, i) {
                    var wrap = Lab.el('div');
                    var label = Lab.el('div', 'small', p[0]); label.style.color = p[2]; label.style.fontWeight = '700';
                    wrap.appendChild(label);
                    var raw = Lab.el('code', 'small', p[1]); raw.style.wordBreak = 'break-all'; raw.style.color = p[2]; wrap.appendChild(raw);
                    if (i < 2) { try { wrap.appendChild(Lab.el('pre', 'small', JSON.stringify(unb64url(p[1]), null, 2))); } catch (e) {} }
                    else wrap.appendChild(Lab.el('p', 'small muted', 'HMAC-SHA256(header + "." + payload, server secret). Not decodable — only recomputable by someone who has the secret.'));
                    box.appendChild(wrap);
                });
            }
            function tick() {
                var now = Math.floor(Date.now() / 1000);
                document.getElementById('jwtTtl').textContent = jwtExp ? Math.max(0, jwtExp - now) + ' s' : '—';
                document.getElementById('cookieTtl').textContent = cookieExp ? Math.max(0, cookieExp - now) + ' s' : '—';
                document.getElementById('cookieVisible').textContent = document.cookie.indexOf('lab_sid') !== -1 ? 'lab_sid=… (!)' : 'nothing (HttpOnly)';
            }
            setInterval(tick, 1000);
            async function sessions() {
                var res = await api('/lab/api/auth/sessions'); var body = document.getElementById('sessions'); clear(body);
                res.d.sessions.forEach(function (s) { var tr = Lab.el('tr'); tr.appendChild(Lab.el('td', 'key', s.sid + (s.mine ? '  ← you' : ''))); tr.appendChild(Lab.el('td', null, s.user)); tr.appendChild(Lab.el('td', null, s.expires_in + ' s')); body.appendChild(tr); });
                if (!res.d.sessions.length) { var tr = Lab.el('tr'); tr.appendChild(Lab.el('td', 'muted small', 'empty')); body.appendChild(tr); }
            }
            setInterval(sessions, 2000); sessions();

            document.getElementById('loginCookie').addEventListener('click', async function () {
                var ttl = parseInt(ttlIn.value, 10);
                wire.add('out', 'POST /lab/api/auth/login {mode: "cookie", ttl: ' + ttl + '}');
                var res = await api('/lab/api/auth/login', { method: 'POST', body: { mode: 'cookie', ttl: ttl } });
                wire.add('in', '200  Set-Cookie: lab_sid=' + res.d.sid_preview + '; HttpOnly; SameSite=Lax; Max-Age=' + ttl + '\n' + res.d.note);
                cookieExp = Math.floor(Date.now() / 1000) + ttl;
                document.getElementById('cookieDot').className = 'status-dot on'; document.getElementById('cookieState').textContent = 'logged in as alice';
                tick(); sessions();
            });
            document.getElementById('loginJwt').addEventListener('click', async function () {
                var ttl = parseInt(ttlIn.value, 10);
                wire.add('out', 'POST /lab/api/auth/login {mode: "jwt", ttl: ' + ttl + '}');
                var res = await api('/lab/api/auth/login', { method: 'POST', body: { mode: 'jwt', ttl: ttl } });
                token = res.d.token; jwtExp = res.d.claims.exp;
                wire.add('in', '200  {token: "' + token.slice(0, 24) + '…"}\n' + res.d.note);
                document.getElementById('jwtDot').className = 'status-dot on'; document.getElementById('jwtState').textContent = 'token held in memory';
                showParts(token); tick();
            });
            document.getElementById('meCookie').addEventListener('click', async function () {
                wire.add('out', 'GET /lab/api/auth/me   (browser attaches lab_sid cookie automatically, if it has one)');
                var res = await api('/lab/api/auth/me');
                wire.add(res.r.ok ? 'in' : 'err', res.r.status + '  ' + (res.r.ok ? res.d.user + ' / ' + res.d.role + ' · ' + res.d.expires_in + ' s left · ' + res.d.note : res.d.error));
                if (!res.r.ok) { document.getElementById('cookieDot').className = 'status-dot off'; document.getElementById('cookieState').textContent = 'rejected'; cookieExp = null; }
            });
            document.getElementById('meJwt').addEventListener('click', async function () {
                if (!token) { wire.add('err', 'no token — log in with JWT first'); return; }
                wire.add('out', 'GET /lab/api/auth/me\nAuthorization: Bearer ' + token.slice(0, 20) + '…');
                var res = await api('/lab/api/auth/me', { headers: { Authorization: 'Bearer ' + token } });
                wire.add(res.r.ok ? 'in' : 'err', res.r.status + '  ' + (res.r.ok ? res.d.user + ' / ' + res.d.role + ' · ' + res.d.expires_in + ' s left · ' + res.d.note : res.d.error));
                if (!res.r.ok) { document.getElementById('jwtDot').className = 'status-dot off'; document.getElementById('jwtState').textContent = 'rejected'; }
            });
            document.getElementById('tamper').addEventListener('click', function () {
                if (!token) { wire.add('err', 'no token yet'); return; }
                var parts = token.split('.'); var claims = unb64url(parts[1]); claims.role = 'admin';
                token = parts[0] + '.' + b64url(claims) + '.' + parts[2];
                wire.add('sys', 'payload edited: role → "admin". The signature was left as it was — which is the only option without the server secret.');
                showParts(token); document.getElementById('jwtState').textContent = 'tampered — press Who am I?';
            });
            document.getElementById('logout').addEventListener('click', async function () {
                wire.add('out', 'POST /lab/api/auth/logout'); var res = await api('/lab/api/auth/logout', { method: 'POST' });
                wire.add('in', '200  server session ' + (res.d.removed ? 'deleted' : 'was not there') + '; cookie cleared');
                cookieExp = null; document.getElementById('cookieDot').className = 'status-dot'; document.getElementById('cookieState').textContent = 'logged out'; sessions();
            });
            document.getElementById('revoke').addEventListener('click', async function () {
                wire.add('out', 'POST /lab/api/auth/revoke-all'); var res = await api('/lab/api/auth/revoke-all', { method: 'POST' });
                wire.add('sys', 'revoked ' + res.d.revoked + ' session(s). ' + res.d.note); sessions();
            });
        }

        /* ================================================================ */
        if (page === 'csrf') {
            var protect = document.getElementById('protect');
            async function load() {
                var res = await api('/lab/api/auth/profile');
                document.getElementById('loginNeeded').hidden = res.r.ok; document.getElementById('profileBox').hidden = !res.r.ok;
                if (res.r.ok) {
                    document.getElementById('who').textContent = res.d.user;
                    var em = document.getElementById('email'); var was = em.textContent; em.textContent = res.d.profile.email;
                    if (was && was !== res.d.profile.email && res.d.profile.email === 'hacked@evil.example') em.style.color = 'var(--danger)'; else if (res.d.profile.email !== 'hacked@evil.example') em.style.color = '';
                    protect.checked = res.d.csrf_required;
                    document.getElementById('tokenShow').textContent = res.d.csrf_required ? 'csrf_token for your session: ' + res.d.csrf_token : '';
                    window._csrf = res.d.csrf_token;
                }
                return res;
            }
            load();
            document.getElementById('login').addEventListener('click', async function () {
                wire.add('out', 'POST /lab/api/auth/login {mode: "cookie", ttl: 600}');
                await api('/lab/api/auth/login', { method: 'POST', body: { mode: 'cookie', ttl: 600 } });
                wire.add('in', 'Set-Cookie: lab_sid=…; HttpOnly; SameSite=Lax'); load();
            });
            document.getElementById('legitForm').addEventListener('submit', async function (e) {
                e.preventDefault();
                var email = document.getElementById('newEmail').value;
                var headers = protect.checked ? { 'X-CSRF-Token': window._csrf } : {};
                wire.add('out', 'POST /lab/api/auth/profile {email: "' + email + '"}' + (protect.checked ? '\nX-CSRF-Token: ' + window._csrf : ''));
                var res = await api('/lab/api/auth/profile', { method: 'POST', body: { email: email }, headers: headers });
                wire.add(res.r.ok ? 'in' : 'err', res.r.status + ' ' + (res.r.ok ? 'email changed' : res.d.error)); load();
            });
            protect.addEventListener('change', async function () {
                await api('/lab/api/auth/csrf/protect', { method: 'POST', body: { enabled: protect.checked } });
                wire.add('sys', 'server now ' + (protect.checked ? 'REQUIRES' : 'does not require') + ' a CSRF token on POST /profile'); load();
            });
            document.getElementById('refresh').addEventListener('click', async function () {
                wire.add('out', 'GET /lab/api/auth/profile'); var res = await load();
                if (res.r.ok) wire.add(res.d.profile.email === 'hacked@evil.example' ? 'err' : 'in', 'email is now: ' + res.d.profile.email + (res.d.profile.email === 'hacked@evil.example' ? '   ← the attacker page did this' : ''));
            });
            window.addEventListener('focus', load);
        }

        /* ================================================================ */
        if (page === 'totp') {
            var peekTimer = null;
            async function peek() {
                var res = await api('/lab/api/auth/totp/peek');
                if (!res.r.ok) return;
                document.getElementById('serverCode').textContent = res.d.code.slice(0, 3) + ' ' + res.d.code.slice(3);
                document.getElementById('left').textContent = res.d.seconds_left + ' s left in this window';
                document.getElementById('windowBar').style.width = (res.d.seconds_left / 30 * 100) + '%';
                document.getElementById('counter').textContent = res.d.counter + '  (= floor(now / 30))';
                document.getElementById('prev').textContent = res.d.previous; document.getElementById('next').textContent = res.d.next;
                document.getElementById('formula').textContent = res.d.hmac_input + ' → dynamic truncation → mod 1 000 000';
                window._peek = res.d;
            }
            document.getElementById('enrol').addEventListener('click', async function () {
                wire.add('out', 'POST /lab/api/auth/totp/enrol');
                var res = await api('/lab/api/auth/totp/enrol', { method: 'POST' });
                wire.add('in', '200  secret (base32): ' + res.d.secret + '\n' + res.d.uri);
                document.getElementById('enrolBox').hidden = false;
                document.getElementById('qr').src = 'data:image/png;base64,' + res.d.qr;
                document.getElementById('secret').textContent = res.d.secret; document.getElementById('uri').textContent = res.d.uri;
                clear(document.getElementById('verdict'));
                if (peekTimer) clearInterval(peekTimer); peek(); peekTimer = setInterval(peek, 1000);
            });
            document.getElementById('verifyForm').addEventListener('submit', async function (e) {
                e.preventDefault();
                var code = document.getElementById('code').value.replace(/\s/g, '');
                wire.add('out', 'POST /lab/api/auth/totp/verify {code: "' + code + '"}');
                var res = await api('/lab/api/auth/totp/verify', { method: 'POST', body: { code: code } });
                var v = document.getElementById('verdict'); clear(v);
                if (res.r.ok) { wire.add('in', '200  accepted — ' + res.d.note); v.appendChild(UI.alert('success', 'Accepted: ' + res.d.note + '.')); }
                else { wire.add('err', res.r.status + '  ' + res.d.error); v.appendChild(UI.alert('error', res.d.error)); }
            });
            document.getElementById('useServer').addEventListener('click', function () { if (window._peek) document.getElementById('code').value = window._peek.code; });
            document.getElementById('usePrev').addEventListener('click', function () { if (window._peek) document.getElementById('code').value = window._peek.previous; });
        }
    });
})();
