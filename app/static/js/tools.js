/* The generic tool runner. Reads the form's data attributes, posts it, and
   renders the shared result shape: {message, facts, filename, extra_files,
   text?, rows?, plus tool-specific extras handled by the custom renderers}. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var form = document.getElementById('toolForm');
        if (!form) return;

        var endpoint = form.dataset.endpoint;
        var slug = form.dataset.slug;
        var render = form.dataset.render || 'download';
        var result = document.getElementById('result');
        var inputFrame = document.getElementById('inputPreview');
        var outputFrame = document.getElementById('outputPreview');
        var button = form.querySelector('[type="submit"]');
        var buttonLabel = button.textContent;

        function url(kind, data, name) {
            return '/tools/' + slug + '/' + kind + '/' + encodeURIComponent(data.job_id) +
                   '/' + encodeURIComponent(name);
        }

        /* --- pickers ------------------------------------------------------ */
        form.querySelectorAll('.dropzone').forEach(function (zone) {
            UI.bindDropzone(zone, function (files) {
                if (zone.hasAttribute('data-no-preview') || !inputFrame || !files[0]) return;
                var file = files[0];
                if (file.type.indexOf('image/') === 0) {
                    UI.showLocalImage(inputFrame, file);
                } else if (file.type.indexOf('video/') === 0) {
                    showVideo(inputFrame, URL.createObjectURL(file), 'Original');
                } else {
                    UI.placeholder(inputFrame, file.name);
                }
                if (outputFrame) UI.placeholder(outputFrame, 'The result appears here');
            });
        });

        form.querySelectorAll('input[type="range"]').forEach(function (range) {
            var output = form.querySelector('output[for="' + range.id + '"]');
            if (!output) return;
            var sync = function () {
                var v = parseFloat(range.value);
                output.textContent = (parseFloat(range.step) < 1) ? v.toFixed(2) : String(v);
            };
            sync();
            range.addEventListener('input', sync);
        });

        function showVideo(frame, src, label) {
            var previous = frame.dataset.objectUrl;
            if (previous) { URL.revokeObjectURL(previous); delete frame.dataset.objectUrl; }
            UI.clear(frame);
            var video = UI.el('video');
            video.controls = true; video.preload = 'metadata'; video.muted = true; video.playsInline = true;
            video.setAttribute('aria-label', label);
            video.src = src;
            frame.appendChild(video);
            if (src.indexOf('blob:') === 0) frame.dataset.objectUrl = src;
        }

        /* --- shared pieces ------------------------------------------------ */
        function factsTable(facts) {
            if (!facts || !facts.length) return null;
            var table = UI.el('table', 'data');
            var body = UI.el('tbody');
            facts.forEach(function (pair) {
                var row = UI.el('tr');
                row.appendChild(UI.el('td', 'key', pair[0]));
                row.appendChild(UI.el('td', 'value', String(pair[1])));
                body.appendChild(row);
            });
            table.appendChild(body);
            var wrap = UI.el('div', 'table-wrap');
            wrap.style.marginTop = 'var(--space-4)';
            wrap.appendChild(table);
            return wrap;
        }

        function rowsTable(rows, headers) {
            var table = UI.el('table', 'data');
            if (headers) {
                var head = UI.el('thead'); var hr = UI.el('tr');
                headers.forEach(function (h) { hr.appendChild(UI.el('th', null, h)); });
                head.appendChild(hr); table.appendChild(head);
            }
            var body = UI.el('tbody');
            rows.forEach(function (r) {
                var tr = UI.el('tr');
                tr.appendChild(UI.el('td', 'key', r[0]));
                tr.appendChild(UI.el('td', 'value mono', String(r[1])));
                body.appendChild(tr);
            });
            table.appendChild(body);
            var wrap = UI.el('div', 'table-wrap'); wrap.style.marginTop = 'var(--space-4)';
            wrap.appendChild(table);
            return wrap;
        }

        function downloads(data) {
            var row = UI.el('div', 'btn-row');
            row.style.marginTop = 'var(--space-4)';
            if (data.filename) {
                var main = UI.el('a', 'btn', 'Download ' + data.filename +
                    (data.size ? ' (' + UI.bytes(data.size) + ')' : ''));
                main.href = url('download', data, data.filename);
                main.setAttribute('download', data.filename);
                row.appendChild(main);
            }
            (data.extra_files || []).forEach(function (name) {
                var link = UI.el('a', 'btn btn--secondary', name);
                link.href = url('download', data, name);
                link.setAttribute('download', name);
                row.appendChild(link);
            });
            return row.childNodes.length ? row : null;
        }

        /* --- renderers ---------------------------------------------------- */
        var custom = {
            'palette': function (data, wrap) {
                var grid = UI.el('div', 'swatches');
                grid.style.marginTop = 'var(--space-4)';
                (data.colors || []).forEach(function (c) {
                    var card = UI.el('div', 'swatch');
                    var color = UI.el('div', 'swatch__color'); color.style.background = c.hex;
                    card.appendChild(color);
                    var meta = UI.el('div', 'swatch__meta');
                    var code = UI.el('code', null, c.hex);
                    code.title = 'Click to copy'; code.style.cursor = 'pointer';
                    code.addEventListener('click', function () {
                        if (navigator.clipboard) navigator.clipboard.writeText(c.hex);
                        code.textContent = 'copied'; setTimeout(function () { code.textContent = c.hex; }, 900);
                    });
                    meta.appendChild(code);
                    meta.appendChild(UI.el('span', 'muted', c.rgb + ' · ' + c.share + '%'));
                    card.appendChild(meta);
                    grid.appendChild(card);
                });
                wrap.appendChild(grid);
            },
            'text-diff': function (data, wrap) {
                var list = UI.el('ul', 'diff');
                list.style.marginTop = 'var(--space-4)';
                (data.lines || []).forEach(function (line) {
                    var prefix = line.kind === 'added' ? '+ ' : (line.kind === 'removed' ? '− ' : '  ');
                    list.appendChild(UI.el('li', line.kind, prefix + line.text));
                });
                wrap.appendChild(list);
            },
            'regex': function (data, wrap) {
                var text = form.querySelector('[name="text"]').value;
                var pre = UI.el('pre'); pre.style.marginTop = 'var(--space-4)';
                var cursor = 0;
                (data.matches || []).forEach(function (m) {
                    pre.appendChild(document.createTextNode(text.slice(cursor, m.start)));
                    pre.appendChild(UI.el('mark', 'hit', text.slice(m.start, m.end)));
                    cursor = m.end;
                });
                pre.appendChild(document.createTextNode(text.slice(cursor)));
                wrap.appendChild(pre);
                if (data.group_count > 0 && data.matches.length) {
                    var rows = data.matches.slice(0, 50).map(function (m, i) {
                        return ['#' + (i + 1) + '  ' + m.match, m.groups.map(function (g, gi) { return '$' + (gi + 1) + ' = ' + g; }).join('   ')];
                    });
                    wrap.appendChild(rowsTable(rows, ['Match', 'Groups']));
                }
            }
        };

        function renderResult(data) {
            var wrap = UI.el('div');
            wrap.appendChild(UI.alert('success', data.message || 'Done.'));

            var facts = factsTable(data.facts);
            if (facts) wrap.appendChild(facts);

            if (render === 'text' && data.text !== undefined) {
                var pre = UI.el('pre', null, data.text);
                pre.style.marginTop = 'var(--space-4)';
                pre.style.maxHeight = '420px';
                pre.style.overflow = 'auto';
                wrap.appendChild(pre);
            }
            if (render === 'table' && data.rows) {
                wrap.appendChild(rowsTable(data.rows));
            }
            if (custom[slug]) custom[slug](data, wrap);

            var links = downloads(data);
            if (links) wrap.appendChild(links);

            if (outputFrame && data.filename) {
                if (render === 'image') {
                    UI.clear(outputFrame);
                    var img = UI.el('img'); img.alt = 'Result';
                    img.src = url('preview', data, data.filename);
                    outputFrame.appendChild(img);
                } else if (render === 'video') {
                    showVideo(outputFrame, url('preview', data, data.filename), 'Result');
                }
            }
            return wrap;
        }

        /* --- submit ------------------------------------------------------- */
        form.addEventListener('submit', async function (event) {
            event.preventDefault();
            button.disabled = true;
            button.textContent = 'Working…';
            UI.clear(result);
            result.appendChild(UI.loading('Working…'));
            try {
                var data = await UI.post(endpoint, new FormData(form));
                UI.clear(result);
                result.appendChild(renderResult(data));
            } catch (error) {
                UI.clear(result);
                result.appendChild(UI.alert('error', error.message));
            } finally {
                button.disabled = false;
                button.textContent = buttonLabel;
            }
        });
    });
})();
