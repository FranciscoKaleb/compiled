/* Photo metadata remover: show what is hidden in the file, then strip it. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var form = document.getElementById('metadataForm');
        if (!form) return;

        var result = document.getElementById('result');
        var inputFrame = document.getElementById('inputPreview');
        var outputFrame = document.getElementById('outputPreview');
        var downloadCard = document.getElementById('downloadCard');
        var downloadLink = document.getElementById('downloadLink');
        var sizeNote = document.getElementById('sizeNote');
        var button = form.querySelector('[type="submit"]');
        var buttonLabel = button.textContent;

        form.querySelectorAll('.dropzone').forEach(function (zone) {
            UI.bindDropzone(zone, function (files) {
                if (files[0]) UI.showLocalImage(inputFrame, files[0]);
                downloadCard.hidden = true;
                UI.placeholder(outputFrame, 'The clean copy appears here');
            });
        });

        form.addEventListener('submit', async function (event) {
            event.preventDefault();

            button.disabled = true;
            button.textContent = 'Reading the file…';
            UI.clear(result);
            result.appendChild(UI.loading('Inspecting metadata…'));
            downloadCard.hidden = true;

            try {
                var data = await UI.post('/tools/metadata-remover/run', new FormData(form));

                UI.clear(result);
                result.appendChild(UI.metadataReport(data, 'photo'));

                UI.showImageData(outputFrame, data.preview, 'The photo with metadata removed');

                downloadLink.href = '/tools/metadata-remover/download/' +
                    encodeURIComponent(data.job_id) + '/' + encodeURIComponent(data.filename);
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
