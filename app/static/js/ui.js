/* Shared UI helpers used by the model runner and the tool pages.
   Everything renders through the DOM rather than innerHTML: model output
   (OCR text, tag names, detected labels) is untrusted content. */
window.UI = (function () {

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = String(text);
        return node;
    }

    function clear(node) {
        while (node && node.firstChild) node.removeChild(node.firstChild);
        return node;
    }

    function alert(kind, message) {
        return el('div', 'alert alert--' + kind, message);
    }

    function loading(message) {
        var wrap = el('div', 'loading');
        wrap.appendChild(el('span', 'spinner'));
        wrap.appendChild(el('span', null, message || 'Working…'));
        return wrap;
    }

    function bytes(value) {
        if (value === null || value === undefined) return '—';
        if (value < 1024) return value + ' B';
        if (value < 1024 * 1024) return (value / 1024).toFixed(1) + ' KB';
        return (value / (1024 * 1024)).toFixed(2) + ' MB';
    }

    /* POST and unwrap the {ok, ...} envelope. Throws with the server's own
       message so every caller can just catch. */
    async function post(url, body, options) {
        var init = Object.assign({ method: 'POST' }, options || {});
        if (body instanceof FormData) {
            init.body = body;
        } else if (body !== undefined) {
            init.headers = Object.assign({ 'Content-Type': 'application/json' }, init.headers || {});
            init.body = JSON.stringify(body);
        }

        var response;
        try {
            response = await fetch(url, init);
        } catch (e) {
            throw new Error('Could not reach the server. Is it still running?');
        }

        var data = null;
        try { data = await response.json(); } catch (e) { /* non-JSON error page */ }

        if (!response.ok || (data && data.ok === false)) {
            throw new Error((data && data.error) || ('Request failed (' + response.status + ')'));
        }
        if (!data) throw new Error('The server returned an unreadable response.');
        return data;
    }

    /* A file picker that also accepts drag-and-drop and shows the filename. */
    function bindDropzone(zone, onPick) {
        var input = zone.querySelector('input[type="file"]');
        var name = zone.querySelector('.dropzone__name');
        if (!input) return null;

        var show = function () {
            var files = input.files;
            if (!files || !files.length) return;
            if (name) {
                name.textContent = files.length > 1
                    ? files.length + ' files selected'
                    : files[0].name;
            }
            if (onPick) onPick(files);
        };

        input.addEventListener('change', show);
        ['dragenter', 'dragover'].forEach(function (type) {
            zone.addEventListener(type, function (e) {
                e.preventDefault();
                zone.classList.add('is-over');
            });
        });
        ['dragleave', 'drop'].forEach(function (type) {
            zone.addEventListener(type, function (e) {
                e.preventDefault();
                zone.classList.remove('is-over');
            });
        });
        zone.addEventListener('drop', function (e) {
            if (e.dataTransfer && e.dataTransfer.files.length) {
                input.files = e.dataTransfer.files;
                show();
            }
        });
        return input;
    }

    /* Object URLs are revoked before being replaced — the old pages leaked one
       per file selection. */
    function showLocalImage(frame, file) {
        var previous = frame.dataset.objectUrl;
        if (previous) URL.revokeObjectURL(previous);

        var url = URL.createObjectURL(file);
        frame.dataset.objectUrl = url;

        clear(frame);
        var img = el('img');
        img.src = url;
        img.alt = 'Selected file preview';
        frame.appendChild(img);
        return img;
    }

    function showImage(frame, b64, mime, altText) {
        clear(frame);
        var img = el('img');
        img.src = 'data:' + mime + ';base64,' + b64;
        img.alt = altText || 'Model output';
        frame.appendChild(img);
        return img;
    }

    function showImageData(frame, b64, altText) {
        return showImage(frame, b64, 'image/png', altText);
    }

    function showImageJpeg(frame, b64, altText) {
        return showImage(frame, b64, 'image/jpeg', altText);
    }

    function placeholder(frame, message) {
        clear(frame);
        frame.appendChild(el('p', 'preview-frame__empty', message));
    }

    /* A labelled score list with proportional bars. */
    function scoreList(pairs, unit) {
        var list = el('ul', 'score-list');
        pairs.forEach(function (pair) {
            var label = pair[0], value = pair[1];
            var item = el('li');
            item.appendChild(el('span', 'score-list__label', label));
            item.appendChild(el('span', 'score-list__value',
                value.toFixed(unit === '%' ? 1 : 3) + (unit || '')));

            var bar = el('span', 'score-list__bar');
            var fill = el('span');
            fill.style.width = Math.max(0, Math.min(100, unit === '%' ? value : value * 100)) + '%';
            bar.appendChild(fill);
            item.appendChild(bar);
            list.appendChild(item);
        });
        return list;
    }

    /* A tag/value table for one metadata group; sensitive rows are highlighted. */
    function metadataTable(group) {
        var wrap = el('div');
        wrap.style.marginBottom = 'var(--space-4)';
        wrap.appendChild(el('p', 'result__summary', group.title));

        var scroller = el('div', 'table-wrap');
        var table = el('table', 'data');
        var head = el('thead');
        var headRow = el('tr');
        headRow.appendChild(el('th', null, 'Tag'));
        headRow.appendChild(el('th', null, 'Value'));
        head.appendChild(headRow);
        table.appendChild(head);

        var body = el('tbody');
        group.rows.forEach(function (row) {
            var tr = el('tr', row.sensitive ? 'is-sensitive' : null);
            tr.appendChild(el('td', 'key', row.tag));
            tr.appendChild(el('td', 'value', row.value));
            body.appendChild(tr);
        });
        table.appendChild(body);
        scroller.appendChild(table);
        wrap.appendChild(scroller);
        return wrap;
    }

    /* The shared "what was in the file" report for the metadata tools. */
    function metadataReport(data, noun) {
        var wrap = el('div');
        if (data.had_location) {
            wrap.appendChild(alert('error',
                'This ' + noun + ' recorded where it was taken: ' + data.location));
        }
        var headline = data.removed > 0
            ? alert('success', 'Removed ' + data.removed + ' metadata entr' +
                (data.removed === 1 ? 'y' : 'ies') + '.')
            : alert('warn', 'This ' + noun + ' carried no removable metadata. The clean ' +
                'copy is still rewritten from the raw content.');
        headline.style.marginTop = data.had_location ? 'var(--space-3)' : '0';
        wrap.appendChild(headline);

        var groups = el('div');
        groups.style.marginTop = 'var(--space-5)';
        (data.before.groups || []).forEach(function (group) {
            if (group.rows.length) groups.appendChild(metadataTable(group));
        });
        if (data.after.count > 0) {
            groups.appendChild(alert('warn',
                data.after.count + ' entr' + (data.after.count === 1 ? 'y' : 'ies') +
                ' remain in the clean copy — these describe the content itself ' +
                '(size, duration, codec), not you.'));
        }
        wrap.appendChild(groups);
        return wrap;
    }

    return {
        el: el, clear: clear, alert: alert, loading: loading, bytes: bytes,
        post: post, bindDropzone: bindDropzone, showLocalImage: showLocalImage,
        showImage: showImage, showImageData: showImageData,
        showImageJpeg: showImageJpeg, placeholder: placeholder, scoreList: scoreList,
        metadataTable: metadataTable, metadataReport: metadataReport
    };
})();
