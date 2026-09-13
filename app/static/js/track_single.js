/* Single object tracking: drag a box, then stream frames to the server. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var video = document.getElementById('video');
        var overlay = document.getElementById('overlay');
        var capture = document.getElementById('capture');
        var frame = document.getElementById('trackedFrame');
        var result = document.getElementById('result');
        if (!video || !overlay) return;

        var camera = Webcam.create(video);
        var startBtn = document.getElementById('startCamera');
        var stopBtn = document.getElementById('stopTracking');

        var sessionId = null;
        var running = false;
        var drag = null;

        function say(node) { UI.clear(result); result.appendChild(node); }

        function sizeOverlay() {
            overlay.width = video.videoWidth || 640;
            overlay.height = video.videoHeight || 480;
            overlay.style.width = video.clientWidth + 'px';
            overlay.style.height = video.clientHeight + 'px';
        }

        function toVideoSpace(event) {
            var rect = overlay.getBoundingClientRect();
            return {
                x: Math.round((event.clientX - rect.left) * (overlay.width / rect.width)),
                y: Math.round((event.clientY - rect.top) * (overlay.height / rect.height))
            };
        }

        function drawBox(box) {
            var context = overlay.getContext('2d');
            context.clearRect(0, 0, overlay.width, overlay.height);
            if (!box) return;
            context.strokeStyle = '#04AA6D';
            context.lineWidth = 3;
            context.strokeRect(box.x, box.y, box.w, box.h);
        }

        startBtn.addEventListener('click', async function () {
            startBtn.disabled = true;
            try {
                await camera.start();
                sizeOverlay();
                stopBtn.disabled = false;
                say(UI.el('p', 'small muted', 'Drag a box around your target.'));
            } catch (error) {
                startBtn.disabled = false;
                say(UI.alert('error', error.message));
            }
        });

        window.addEventListener('resize', function () {
            if (camera.active) sizeOverlay();
        });

        overlay.addEventListener('pointerdown', function (event) {
            if (!camera.active) return;
            var point = toVideoSpace(event);
            drag = { x: point.x, y: point.y, w: 0, h: 0 };
            overlay.setPointerCapture(event.pointerId);
        });

        overlay.addEventListener('pointermove', function (event) {
            if (!drag) return;
            var point = toVideoSpace(event);
            drawBox({
                x: Math.min(drag.x, point.x),
                y: Math.min(drag.y, point.y),
                w: Math.abs(point.x - drag.x),
                h: Math.abs(point.y - drag.y)
            });
        });

        overlay.addEventListener('pointerup', async function (event) {
            if (!drag) return;
            var point = toVideoSpace(event);
            var box = {
                x: Math.min(drag.x, point.x),
                y: Math.min(drag.y, point.y),
                w: Math.abs(point.x - drag.x),
                h: Math.abs(point.y - drag.y)
            };
            drag = null;

            if (box.w < 5 || box.h < 5) {
                drawBox(null);
                say(UI.alert('warn', 'That box was too small — drag a larger one.'));
                return;
            }

            say(UI.loading('Starting the tracker…'));
            try {
                var data = await UI.post('/models/track/single/init', {
                    x: box.x, y: box.y, w: box.w, h: box.h,
                    frame: camera.grabRaw(capture)
                });
                sessionId = data.session_id;
                running = true;
                drawBox(null);
                UI.showImageJpeg(frame, data.frame, 'Selected target');
                say(UI.el('p', 'small muted', 'Tracking with ' + data.algorithm + '.'));
                loop();
            } catch (error) {
                say(UI.alert('error', error.message));
            }
        });

        async function loop() {
            if (!running || !sessionId) return;
            try {
                var data = await UI.post('/models/track/single/update', {
                    session_id: sessionId,
                    frame: camera.grabRaw(capture)
                });
                UI.showImageJpeg(frame, data.frame, 'Tracked frame');
                if (!data.tracking) {
                    say(UI.alert('warn', 'Target lost — stop and draw a new box.'));
                }
            } catch (error) {
                running = false;
                say(UI.alert('error', error.message));
                return;
            }
            setTimeout(loop, 120);
        }

        async function teardown() {
            running = false;
            if (sessionId) {
                try { await UI.post('/models/track/single/stop', { session_id: sessionId }); }
                catch (e) { /* the session expires on its own anyway */ }
                sessionId = null;
            }
            camera.stop();
            drawBox(null);
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
