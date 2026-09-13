/* Filter the model catalogue as you type. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var search = document.getElementById('modelSearch');
        var empty = document.getElementById('noMatches');
        if (!search) return;

        search.addEventListener('input', function () {
            var query = search.value.trim().toLowerCase();
            var total = 0;

            document.querySelectorAll('[data-section]').forEach(function (section) {
                var shown = 0;
                section.querySelectorAll('[data-search]').forEach(function (tile) {
                    var hit = !query || tile.dataset.search.indexOf(query) !== -1;
                    tile.hidden = !hit;
                    if (hit) shown += 1;
                });
                section.hidden = shown === 0;
                total += shown;
            });

            if (empty) empty.hidden = total !== 0;
        });
    });
})();
