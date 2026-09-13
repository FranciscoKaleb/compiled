/* A dedicated worker: receives {n}, does the same heavy loop as the main-thread
   version, posts progress and the result. Nothing here can touch the DOM. */
self.onmessage = function (e) {
    var n = e.data.n, started = performance.now(), acc = 0;
    var chunk = Math.max(1, Math.floor(n / 20));
    for (var i = 1; i <= n; i++) {
        acc += Math.sin(i) * Math.cos(i / 3) / (1 + (i % 7));
        if (i % chunk === 0) self.postMessage({ progress: i / n });
    }
    self.postMessage({ done: true, result: acc, ms: Math.round(performance.now() - started) });
};
