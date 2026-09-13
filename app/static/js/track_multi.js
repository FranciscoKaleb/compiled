/* Multi object tracking: background subtraction + SORT, server side. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var video = document.getElementById('video');
        var capture = document.getElementById('capture');
        var frame = document.getElementById('trackedFrame');
        var result = document.getElementById('result');
        if (!video || !capture) return;

        var camera = Webcam.create(video);
        var startBtn = document.getElementById('startCamera');
        var stopBtn = document.getElementById('stopTracking');
        var minArea = document.getElementById('min_area');
        var activeCount = document.getElementById('activeCount');
        var uniqueCount = document.getElementById('uniqueCount');

        var sessionId = null;
        var running = false;

        function say(node) { UI.clear(result); result.appendChild(node); }

        var output = document.querySelector('output[for="min_area"]');
        if (minArea && output) {
            var sync = function () { output.textContent = minArea.value; };
            sync();
            minArea.addEventListener('input', sync);
        }

        startBtn.addEventListener('click', async function () {
            startBtn.disabled = true;
            say(UI.loading('Starting the camera…'));
            try {
                await camera.start();
                var data = await UI.post('/models/track/multi/init', {
                    min_area: minArea ? parseInt(minArea.value, 10) : 500
                });
                sessionId = data.session_id;
                running = true;
                stopBtn.disabled = false;
                say(UI.el('p', 'small muted', 'Tracking. Move something in frame.'));
                loop();
            } catch (error) {
                startBtn.disabled = false;
                camera.stop();
                say(UI.alert('error', error.message));
            }
        });

        async function loop() {
            if (!running || !sessionId) return;
            try {
                var data = await UI.post('/models/track/multi/update', {
                    session_id: sessionId,
                    frame: camera.grabRaw(capture),
                    min_area: minArea ? parseInt(minArea.value, 10) : 500
                });
                UI.showImageJpeg(frame, data.frame, 'Tracked frame');
                activeCount.textContent = data.active;
                uniqueCount.textContent = data.unique_ids;
            } catch (error) {
                running = false;
                say(UI.alert('error', error.message));
                return;
            }
            setTimeout(loop, 140);
        }

        async function teardown() {
            running = false;
            if (sessionId) {
                try { await UI.post('/models/track/multi/stop', { session_id: sessionId }); }
                catch (e) { /* expires on its own */ }
                sessionId = null;
            }
            camera.stop();
            startBtn.disabled = false;
            stopBtn.disabled = true;
        }

        stopBtn.addEventListener('click', function () {
            teardown();
            say(UI.el('p', 'small muted', 'Stopped.'));
        });
        window.addEventListener('pagehide', teardown);
    });
})();
