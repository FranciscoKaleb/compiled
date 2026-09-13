/* Start and stop an MJPEG stream.
   Clearing the <img> src is what actually closes the HTTP connection, which
   lets the server release the camera in its finally block. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var start = document.getElementById('startStream');
        var stop = document.getElementById('stopStream');
        var frame = document.getElementById('streamFrame');
        var result = document.getElementById('result');
        if (!start || !frame) return;

        var image = null;

        start.addEventListener('click', function () {
            UI.clear(frame);
            UI.clear(result);

            image = UI.el('img');
            image.alt = window.STREAM_ALT || 'Live camera stream';
            image.addEventListener('error', function () {
                UI.clear(result);
                result.appendChild(UI.alert('error',
                    'The stream stopped. The server may have no camera available.'));
                teardown();
            });
            image.src = window.STREAM_URL + '?t=' + Date.now();
            frame.appendChild(image);

            start.disabled = true;
            stop.disabled = false;
        });

        function teardown() {
            if (image) {
                image.src = '';
                image.remove();
                image = null;
            }
            UI.placeholder(frame, 'The stream appears here.');
            start.disabled = false;
            stop.disabled = true;
        }

        stop.addEventListener('click', teardown);
        window.addEventListener('pagehide', teardown);
    });
})();
