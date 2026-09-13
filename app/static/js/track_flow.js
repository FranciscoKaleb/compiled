/* Optical flow: upload a clip, then play the traced frames back. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var form = document.getElementById('flowForm');
        var frame = document.getElementById('flowFrame');
        var result = document.getElementById('result');
        if (!form) return;

        var card = document.getElementById('playbackCard');
        var playPause = document.getElementById('playPause');
        var restart = document.getElementById('restart');
        var scrub = document.getElementById('scrub');
        var scrubOut = document.querySelector('output[for="scrub"]');
        var button = form.querySelector('[type="submit"]');

        var frames = [];
        var index = 0;
        var timer = null;
        var image = null;

        form.querySelectorAll('.dropzone').forEach(function (zone) {
            UI.bindDropzone(zone);
        });

        function show(i) {
            if (!frames.length) return;
            index = Math.max(0, Math.min(frames.length - 1, i));
            if (!image) {
                UI.clear(frame);
                image = UI.el('img');
                image.alt = 'Optical flow trails over the video';
                frame.appendChild(image);
            }
            image.src = 'data:image/jpeg;base64,' + frames[index];
            scrub.value = index;
            if (scrubOut) scrubOut.textContent = index + 1;
        }

        function play(fps) {
            stop();
            timer = setInterval(function () {
                show(index + 1 >= frames.length ? 0 : index + 1);
            }, Math.max(33, 1000 / (fps || 25)));
            playPause.textContent = 'Pause';
        }

        function stop() {
            if (timer) { clearInterval(timer); timer = null; }
            playPause.textContent = 'Play';
        }

        form.addEventListener('submit', async function (event) {
            event.preventDefault();
            stop();

            button.disabled = true;
            var label = button.textContent;
            button.textContent = 'Processing…';
            UI.clear(result);
            result.appendChild(UI.loading('Tracing motion through the video…'));

            try {
                var data = await UI.post('/models/track/flow/predict', new FormData(form));
                frames = data.frames || [];
                image = null;
                if (!frames.length) {
                    throw new Error('No frames came back from that video.');
                }
                scrub.max = frames.length - 1;
                card.hidden = false;
                show(0);
                play(data.fps);
                UI.clear(result);
                result.appendChild(UI.el('p', 'small muted',
                    frames.length + ' frames at ' + data.fps + ' fps.'));
            } catch (error) {
                UI.clear(result);
                result.appendChild(UI.alert('error', error.message));
            } finally {
                button.disabled = false;
                button.textContent = label;
            }
        });

        playPause.addEventListener('click', function () {
            if (timer) { stop(); } else { play(25); }
        });
        restart.addEventListener('click', function () { show(0); });
        scrub.addEventListener('input', function () {
            stop();
            show(parseInt(scrub.value, 10));
        });
        window.addEventListener('pagehide', stop);
    });
})();
