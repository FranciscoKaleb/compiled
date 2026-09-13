/* Face enrolment and identification. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var video = document.getElementById('video');
        var canvas = document.getElementById('capture');
        var result = document.getElementById('result');
        if (!video || !canvas) return;

        var camera = Webcam.create(video);
        var startBtn = document.getElementById('startCamera');
        var stopBtn = document.getElementById('stopCamera');
        var enrolBtn = document.getElementById('enrol');
        var identifyBtn = document.getElementById('identify');
        var nameInput = document.getElementById('personName');

        function setReady(ready) {
            enrolBtn.disabled = !ready;
            identifyBtn.disabled = !ready;
            stopBtn.disabled = !ready;
            startBtn.disabled = ready;
        }

        function say(node) {
            UI.clear(result);
            result.appendChild(node);
        }

        startBtn.addEventListener('click', async function () {
            startBtn.disabled = true;
            try {
                await camera.start();
                setReady(true);
                say(UI.el('p', 'small muted', 'Camera running. Capture when you are ready.'));
            } catch (error) {
                startBtn.disabled = false;
                say(UI.alert('error', error.message));
            }
        });

        stopBtn.addEventListener('click', function () {
            camera.stop();
            setReady(false);
            say(UI.el('p', 'small muted', 'Camera stopped.'));
        });

        window.addEventListener('pagehide', function () { camera.stop(); });

        async function send(url, payload, busy) {
            enrolBtn.disabled = true;
            identifyBtn.disabled = true;
            say(UI.loading(busy));
            try {
                return await UI.post(url, payload);
            } finally {
                if (camera.active) {
                    enrolBtn.disabled = false;
                    identifyBtn.disabled = false;
                }
            }
        }

        enrolBtn.addEventListener('click', async function () {
            var name = nameInput.value.trim();
            if (!name) {
                say(UI.alert('warn', 'Enter a name first.'));
                nameInput.focus();
                return;
            }
            try {
                var data = await send(
                    window.location.pathname + '/enroll',
                    { name: name, image: camera.grab(canvas) },
                    'Enrolling…'
                );
                say(UI.alert('success', data.message));
                nameInput.value = '';
                loadRoster();
            } catch (error) {
                say(UI.alert('error', error.message));
            }
        });

        identifyBtn.addEventListener('click', async function () {
            try {
                var data = await send(
                    window.location.pathname + '/match',
                    { image: camera.grab(canvas) },
                    'Matching…'
                );
                var wrap = UI.el('div');
                wrap.appendChild(UI.alert(data.matched ? 'success' : 'warn', data.message));
                if (data.similarity) {
                    var meter = UI.el('div');
                    meter.style.marginTop = 'var(--space-4)';
                    meter.appendChild(UI.scoreList([['Similarity', data.similarity]], ''));
                    wrap.appendChild(meter);
                }
                say(wrap);
            } catch (error) {
                say(UI.alert('error', error.message));
            }
        });

        /* --- roster ------------------------------------------------------ */

        var roster = document.getElementById('roster');
        var rosterCount = document.getElementById('rosterCount');
        var rosterEmpty = document.getElementById('rosterEmpty');

        async function loadRoster() {
            try {
                var response = await fetch(window.location.pathname + '/roster');
                var data = await response.json();
                var people = data.people || [];

                UI.clear(roster);
                rosterCount.textContent = people.length;
                rosterEmpty.hidden = people.length > 0;

                people.forEach(function (person) {
                    var item = UI.el('li');
                    var label = UI.el('span');
                    label.appendChild(UI.el('strong', null, person.name));
                    label.appendChild(document.createTextNode(' '));
                    label.appendChild(UI.el('span', 'small muted',
                        person.samples + ' sample' + (person.samples === 1 ? '' : 's')));
                    item.appendChild(label);

                    var remove = UI.el('button', 'btn btn--secondary btn--small', 'Forget');
                    remove.type = 'button';
                    remove.addEventListener('click', async function () {
                        remove.disabled = true;
                        try {
                            await UI.post(window.location.pathname + '/roster/' + person.id,
                                          undefined, { method: 'DELETE' });
                            loadRoster();
                        } catch (error) {
                            say(UI.alert('error', error.message));
                            remove.disabled = false;
                        }
                    });
                    item.appendChild(remove);
                    roster.appendChild(item);
                });
            } catch (e) {
                rosterEmpty.textContent = 'Could not load the enrolled people.';
                rosterEmpty.hidden = false;
            }
        }

        loadRoster();
    });
})();
