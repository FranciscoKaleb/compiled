/* Browser camera access, shared by the face and tracking pages.
   Handles the permission-denied and no-camera cases the old pages ignored. */
window.Webcam = (function () {

    function create(video, options) {
        var stream = null;

        return {
            get active() { return stream !== null; },

            async start() {
                if (stream) return stream;
                if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                    throw new Error('This browser cannot access a camera.');
                }
                try {
                    stream = await navigator.mediaDevices.getUserMedia({
                        video: options || { width: 640, height: 480 },
                        audio: false
                    });
                } catch (error) {
                    if (error && error.name === 'NotAllowedError') {
                        throw new Error('Camera access was denied. Allow it in your browser and retry.');
                    }
                    if (error && error.name === 'NotFoundError') {
                        throw new Error('No camera was found on this device.');
                    }
                    throw new Error('Could not start the camera: ' + (error.message || error.name));
                }
                video.srcObject = stream;
                await video.play();
                return stream;
            },

            stop() {
                if (!stream) return;
                stream.getTracks().forEach(function (track) { track.stop(); });
                stream = null;
                video.srcObject = null;
            },

            /* A base64 JPEG of the current frame, sized to the video itself. */
            grab(canvas, quality) {
                var width = video.videoWidth || 640;
                var height = video.videoHeight || 480;
                canvas.width = width;
                canvas.height = height;
                canvas.getContext('2d').drawImage(video, 0, 0, width, height);
                return canvas.toDataURL('image/jpeg', quality || 0.85);
            },

            /* Just the payload, for endpoints that want raw base64. */
            grabRaw(canvas, quality) {
                return this.grab(canvas, quality).split(',')[1];
            }
        };
    }

    return { create: create };
})();
