/* Video metadata remover: inspect, strip via ffmpeg, preview the clean copy. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var form = document.getElementById('videoMetadataForm');
        if (!form) return;

        var result = document.getElementById('result');
        var inputFrame = document.getElementById('inputPreview');
        var outputFrame = document.getElementById('outputPreview');
        var downloadCard = document.getElementById('downloadCard');
        var downloadLink = document.getElementById('downloadLink');
        var sizeNote = document.getElementById('sizeNote');
        var button = form.querySelector('[type="submit"]');
        var buttonLabel = button.textContent;

        function showVideo(frame, src, label) {
            var previous = frame.dataset.objectUrl;
            if (previous) { URL.revokeObjectURL(previous); delete frame.dataset.objectUrl; }
            UI.clear(frame);
            var video = UI.el('video');
            video.controls = true;
            video.preload = 'metadata';
            video.muted = true;
            video.playsInline = true;
            video.setAttribute('aria-label', label);
            video.src = src;
            frame.appendChild(video);
            return video;
        }

        form.querySelectorAll('.dropzone').forEach(function (zone) {
            UI.bindDropzone(zone, function (files) {
                if (!files[0]) return;
                var url = URL.createObjectURL(files[0]);
                showVideo(inputFrame, url, 'Original video');
                inputFrame.dataset.objectUrl = url;
                downloadCard.hidden = true;
                UI.placeholder(outputFrame, 'The clean copy appears here');
            });
        });

        form.addEventListener('submit', async function (event) {
            event.preventDefault();

            button.disabled = true;
            button.textContent = 'Uploading and rewriting…';
            UI.clear(result);
            result.appendChild(UI.loading('Reading tags and copying streams…'));
            downloadCard.hidden = true;

            try {
                var data = await UI.post('/tools/video-metadata-remover/run', new FormData(form));

                UI.clear(result);
                result.appendChild(UI.metadataReport(data, 'video'));

                var base = '/tools/video-metadata-remover/';
                var tail = encodeURIComponent(data.job_id) + '/' + encodeURIComponent(data.filename);
                showVideo(outputFrame, base + 'preview/' + tail, 'Video with metadata removed');

                downloadLink.href = base + 'download/' + tail;
                downloadLink.setAttribute('download', data.filename);
                sizeNote.textContent = 'Clean file: ' + UI.bytes(data.size_after) + '.';
                downloadCard.hidden = false;
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
