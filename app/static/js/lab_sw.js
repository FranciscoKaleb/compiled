/* The Web Lab service worker. Scope: /lab/offline (set at registration).
   Three strategies, chosen per URL, plus an app-shell precache so the page
   itself loads with the network unplugged. Every decision is reported back to
   the page over postMessage so it can show up in the wire log. */
var VERSION = 'lab-offline-v1';
var SHELL = ['/lab/offline', '/static/css/tokens.css', '/static/css/base.css', '/static/css/layout.css',
             '/static/css/components.css', '/static/js/theme.js', '/static/js/ui.js', '/static/js/lab.js',
             '/static/js/lab_browser.js'];

self.addEventListener('install', function (event) {
    event.waitUntil(caches.open(VERSION).then(function (cache) { return cache.addAll(SHELL); }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (event) {
    event.waitUntil(caches.keys().then(function (keys) {
        return Promise.all(keys.filter(function (k) { return k !== VERSION; }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); }));
});

function tell(event, detail) {
    if (!event.clientId) return;
    self.clients.get(event.clientId).then(function (client) { if (client) client.postMessage(Object.assign({ from: 'sw' }, detail)); });
}

self.addEventListener('fetch', function (event) {
    var url = new URL(event.request.url);
    if (url.origin !== self.location.origin) return;
    var strategy = url.searchParams.get('strategy');

    // The demo API: strategy chosen by the page via a query parameter.
    if (url.pathname === '/lab/api/browser/offline/time') {
        if (strategy === 'network-first') event.respondWith(networkFirst(event));
        else if (strategy === 'stale-while-revalidate') event.respondWith(staleWhileRevalidate(event));
        else if (strategy === 'network-only') event.respondWith(networkOnly(event));
        else event.respondWith(cacheFirst(event));
        return;
    }
    // Everything else under our scope: app shell, cache-first with network fallback.
    if (SHELL.indexOf(url.pathname) !== -1 || url.pathname.indexOf('/static/') === 0) {
        event.respondWith(caches.match(event.request).then(function (hit) {
            if (hit) { tell(event, { strategy: 'shell', source: 'cache', url: url.pathname }); return hit; }
            return fetch(event.request).then(function (res) {
                tell(event, { strategy: 'shell', source: 'network', url: url.pathname });
                return res;
            });
        }));
    }
});

function cacheFirst(event) {
    return caches.match(event.request).then(function (hit) {
        if (hit) { tell(event, { strategy: 'cache-first', source: 'cache' }); return hit; }
        return fetch(event.request).then(function (res) {
            var copy = res.clone(); caches.open(VERSION).then(function (c) { c.put(event.request, copy); });
            tell(event, { strategy: 'cache-first', source: 'network (now cached)' }); return res;
        }).catch(function () { tell(event, { strategy: 'cache-first', source: 'FAILED — offline and nothing cached' }); return offline(); });
    });
}

function networkFirst(event) {
    return fetch(event.request).then(function (res) {
        var copy = res.clone(); caches.open(VERSION).then(function (c) { c.put(event.request, copy); });
        tell(event, { strategy: 'network-first', source: 'network (cache refreshed)' }); return res;
    }).catch(function () {
        return caches.match(event.request).then(function (hit) {
            if (hit) { tell(event, { strategy: 'network-first', source: 'cache (network failed)' }); return hit; }
            tell(event, { strategy: 'network-first', source: 'FAILED — offline and nothing cached' }); return offline();
        });
    });
}

function staleWhileRevalidate(event) {
    return caches.match(event.request).then(function (hit) {
        var refresh = fetch(event.request).then(function (res) {
            var copy = res.clone(); caches.open(VERSION).then(function (c) { c.put(event.request, copy); });
            tell(event, { strategy: 'stale-while-revalidate', source: 'background refresh landed' + (hit ? ' (next read will see it)' : '') });
            return res;
        }).catch(function () { tell(event, { strategy: 'stale-while-revalidate', source: 'background refresh failed (offline)' }); });
        if (hit) { tell(event, { strategy: 'stale-while-revalidate', source: 'cache, instantly' }); return hit; }
        return refresh.then(function (res) { return res || offline(); });
    });
}

function networkOnly(event) {
    return fetch(event.request).then(function (res) { tell(event, { strategy: 'network-only', source: 'network' }); return res; })
        .catch(function () { tell(event, { strategy: 'network-only', source: 'FAILED — offline' }); return offline(); });
}

function offline() {
    return new Response(JSON.stringify({ ok: false, error: 'offline', offline: true }), { status: 503, headers: { 'Content-Type': 'application/json' } });
}

/* Push: show a notification even when no tab is open. */
self.addEventListener('push', function (event) {
    var data = {};
    try { data = event.data ? event.data.json() : {}; } catch (e) { data = { body: event.data && event.data.text() }; }
    event.waitUntil(self.registration.showNotification(data.title || 'Compiled Web Lab', {
        body: (data.body || '') + (data.sent_at ? '  (sent ' + data.sent_at + ')' : ''),
        icon: '/static/icon.png', badge: '/static/icon.png', tag: 'lab-push', renotify: true,
        data: { url: data.url || '/lab/push' }
    }));
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    var target = (event.notification.data && event.notification.data.url) || '/lab/push';
    event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
        for (var i = 0; i < list.length; i++) { if (list[i].url.indexOf(target) !== -1) return list[i].focus(); }
        return self.clients.openWindow(target);
    }));
});
