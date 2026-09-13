/* The "free memory" control in the models sidebar. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var button = document.getElementById('clearCache');
        var status = document.getElementById('cacheStatus');
        if (!button || !status) return;

        async function refresh() {
            try {
                var response = await fetch('/models/cache');
                var data = await response.json();
                var count = (data.loaded || []).length;
                status.textContent = count
                    ? count + ' model(s) in memory'
                    : 'Models load on first use.';
            } catch (e) { /* leave the current text */ }
        }

        refresh();

        button.addEventListener('click', async function () {
            button.disabled = true;
            status.textContent = 'Freeing…';
            try {
                var data = await UI.post('/models/cache/clear');
                status.textContent = data.count
                    ? 'Freed ' + data.count + ' model(s).'
                    : 'Nothing was loaded.';
            } catch (error) {
                status.textContent = error.message;
            } finally {
                button.disabled = false;
                setTimeout(refresh, 2500);
            }
        });
    });
})();
