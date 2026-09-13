/* The one model runner.
   Replaces ~994 lines of inline <script> that were copy-pasted across 27
   templates with only a number changed. Reads its configuration off the form's
   data attributes, so a new model page needs no JavaScript at all. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var form = document.getElementById('runnerForm');
        if (!form) return;

        var endpoint = form.dataset.endpoint;
        var render = form.dataset.render || 'predictions';
        var kind = form.dataset.input || 'image';

        var button = form.querySelector('[type="submit"]');
        var buttonLabel = button ? button.textContent : 'Run';
        var result = document.getElementById('result');
        var inputFrame = document.getElementById('inputPreview');
        var outputFrame = document.getElementById('outputPreview');

        /* --- file pickers and previews --- */
        form.querySelectorAll('.dropzone').forEach(function (zone) {
            UI.bindDropzone(zone, function (files) {
                var frame = zone.dataset.previewTarget
                    ? document.getElementById(zone.dataset.previewTarget)
                    : inputFrame;
                if (frame && files[0] && files[0].type.indexOf('image/') === 0) {
                    UI.showLocalImage(frame, files[0]);
                }
            });
        });

        /* --- range inputs show their value --- */
        form.querySelectorAll('input[type="range"]').forEach(function (range) {
            var output = form.querySelector('output[for="' + range.id + '"]');
            if (!output) return;
            var sync = function () {
                var value = parseFloat(range.value);
                output.textContent = value >= 10 ? value : value.toFixed(2);
            };
            sync();
            range.addEventListener('input', sync);
        });

        /* --- renderers ------------------------------------------------- */

        var renderers = {
            predictions: function (data) {
                if (!data.predictions || !data.predictions.length) {
                    return UI.alert('warn', 'The model returned no predictions.');
                }
                return UI.scoreList(data.predictions, '%');
            },

            label: function (data) {
                var wrap = UI.el('div');
                var head = UI.el('p', 'result__summary', 'Predicted class');
                wrap.appendChild(head);
                var chip = UI.el('span', 'badge', data.label);
                wrap.appendChild(chip);
                wrap.appendChild(UI.el('p', 'small muted',
                    'Confidence ' + data.confidence.toFixed(1) + '%'));
                return wrap;
            },

            sentiment: function (data) {
                var wrap = UI.el('div');
                var tone = data.sentiment.toLowerCase();
                var kindClass = tone.indexOf('pos') === 0 ? 'success'
                    : (tone.indexOf('neg') === 0 ? 'error' : 'warn');
                wrap.appendChild(UI.alert(kindClass,
                    data.sentiment + ' · ' + data.confidence.toFixed(1) + '%'));
                if (data.scores) {
                    var detail = UI.el('div');
                    detail.style.marginTop = 'var(--space-4)';
                    detail.appendChild(UI.scoreList(data.scores, '%'));
                    wrap.appendChild(detail);
                }
                return wrap;
            },

            detections: function (data) {
                if (data.image_data && outputFrame) {
                    UI.showImageData(outputFrame, data.image_data, 'Detections drawn on the image');
                }
                var wrap = UI.el('div');
                if (data.summary) wrap.appendChild(UI.el('p', 'result__summary', data.summary));
                if (!data.detections || !data.detections.length) {
                    wrap.appendChild(UI.el('p', 'small muted', 'Nothing was detected above the threshold.'));
                    return wrap;
                }
                wrap.appendChild(UI.scoreList(
                    data.detections.map(function (d) { return [d.label, d.score]; }), ''
                ));
                return wrap;
            },

            annotated: function (data) {
                return renderers.detections(data);
            },

            segments: function (data) {
                if (data.image_data && outputFrame) {
                    UI.showImageData(outputFrame, data.image_data, 'Segmentation mask over the image');
                }
                var wrap = UI.el('div');
                if (data.summary) wrap.appendChild(UI.el('p', 'result__summary', data.summary));
                var chips = UI.el('div', 'chips');
                (data.segments || []).forEach(function (segment) {
                    var chip = UI.el('span', 'chip');
                    chip.appendChild(UI.el('span', null, segment.label));
                    if (segment.detail) chip.appendChild(UI.el('span', 'chip__score', segment.detail));
                    chips.appendChild(chip);
                });
                wrap.appendChild(chips);
                return wrap;
            },

            text: function (data) {
                if (data.image_data && outputFrame) {
                    UI.showImageData(outputFrame, data.image_data, 'The page that was read');
                }
                var wrap = UI.el('div');
                wrap.appendChild(UI.el('p', 'result__summary', 'Recognised text'));
                if (!data.text || !data.text.trim()) {
                    wrap.appendChild(UI.alert('warn', 'No text was recognised in that image.'));
                    return wrap;
                }
                wrap.appendChild(UI.el('pre', null, data.text));
                return wrap;
            },

            tags: function (data) {
                var wrap = UI.el('div');
                var any = false;
                (data.groups || []).forEach(function (group) {
                    if (!group.items.length) return;
                    any = true;
                    wrap.appendChild(UI.el('p', 'result__summary', group.title));
                    var chips = UI.el('div', 'chips');
                    group.items.forEach(function (item) {
                        var chip = UI.el('span', 'chip');
                        chip.appendChild(UI.el('span', null, item.name));
                        chip.appendChild(UI.el('span', 'chip__score', item.score.toFixed(2)));
                        chips.appendChild(chip);
                    });
                    chips.style.marginBottom = 'var(--space-4)';
                    wrap.appendChild(chips);
                });
                if (!any) return UI.alert('warn', 'No tags cleared the threshold. Try lowering it.');
                return wrap;
            },

            similarity: function (data) {
                var wrap = UI.el('div');
                wrap.appendChild(UI.alert(data.same ? 'success' : 'warn', data.verdict));
                var meter = UI.el('div');
                meter.style.marginTop = 'var(--space-4)';
                meter.appendChild(UI.scoreList([['Cosine similarity', data.similarity]], ''));
                wrap.appendChild(meter);
                wrap.appendChild(UI.el('p', 'small muted',
                    'Threshold for a match: ' + data.threshold.toFixed(2)));
                return wrap;
            }
        };

        /* --- submit ----------------------------------------------------- */

        form.addEventListener('submit', async function (event) {
            event.preventDefault();

            UI.clear(result);
            result.appendChild(UI.loading(form.dataset.busyLabel || 'Running the model…'));
            if (button) {
                button.disabled = true;
                UI.clear(button);
                button.appendChild(UI.el('span', 'spinner'));
                button.appendChild(document.createTextNode(' Working…'));
            }

            try {
                var data = await UI.post(endpoint, new FormData(form));
                UI.clear(result);
                var renderer = renderers[render] || renderers.predictions;
                result.appendChild(renderer(data));
            } catch (error) {
                UI.clear(result);
                result.appendChild(UI.alert('error', error.message));
            } finally {
                if (button) {
                    button.disabled = false;
                    UI.clear(button);
                    button.textContent = buttonLabel;
                }
            }
        });

        if (kind === 'image' || kind === 'two-images') {
            if (outputFrame) UI.placeholder(outputFrame, 'Results appear here');
        }
    });
})();
