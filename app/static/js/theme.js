/* Theme toggle and the responsive sidebar drawer.
   Runs before paint (the script tag is in <head>) so there is no flash of the
   wrong theme. */
(function () {
    var STORAGE_KEY = 'compiled:theme';

    function stored() {
        try { return localStorage.getItem(STORAGE_KEY); } catch (e) { return null; }
    }

    function apply(theme) {
        if (theme === 'dark' || theme === 'light') {
            document.documentElement.setAttribute('data-theme', theme);
        } else {
            document.documentElement.removeAttribute('data-theme');
        }
    }

    apply(stored());

    function effective() {
        var explicit = document.documentElement.getAttribute('data-theme');
        if (explicit) return explicit;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    document.addEventListener('DOMContentLoaded', function () {
        var button = document.getElementById('themeToggle');
        if (button) {
            var sync = function () {
                var dark = effective() === 'dark';
                button.textContent = dark ? '☀' : '☾';
                button.setAttribute('aria-label',
                    dark ? 'Switch to light theme' : 'Switch to dark theme');
            };
            sync();
            button.addEventListener('click', function () {
                var next = effective() === 'dark' ? 'light' : 'dark';
                apply(next);
                try { localStorage.setItem(STORAGE_KEY, next); } catch (e) { /* private mode */ }
                sync();
            });
        }

        /* Sidebar drawer on narrow screens */
        var drawerButton = document.getElementById('sidebarToggle');
        var scrim = document.getElementById('sidebarScrim');
        var close = function () { document.body.removeAttribute('data-drawer'); };

        if (drawerButton) {
            drawerButton.addEventListener('click', function () {
                var open = document.body.getAttribute('data-drawer') === 'open';
                if (open) { close(); } else { document.body.setAttribute('data-drawer', 'open'); }
                drawerButton.setAttribute('aria-expanded', String(!open));
            });
        }
        if (scrim) scrim.addEventListener('click', close);
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') close();
        });

        /* Sidebar accordion — real buttons, state remembered per group. */
        var ACCORDION_KEY = 'compiled:sidebar';
        var state = {};
        try { state = JSON.parse(localStorage.getItem(ACCORDION_KEY)) || {}; } catch (e) { state = {}; }

        document.querySelectorAll('.sidebar__toggle').forEach(function (toggle) {
            var group = toggle.dataset.group;
            var hasCurrent = toggle.nextElementSibling &&
                toggle.nextElementSibling.querySelector('[aria-current="page"]');

            if (hasCurrent) {
                toggle.setAttribute('aria-expanded', 'true');
            } else if (group in state) {
                toggle.setAttribute('aria-expanded', String(state[group]));
            }

            toggle.addEventListener('click', function () {
                var open = toggle.getAttribute('aria-expanded') === 'true';
                toggle.setAttribute('aria-expanded', String(!open));
                state[group] = !open;
                try { localStorage.setItem(ACCORDION_KEY, JSON.stringify(state)); } catch (e) { /* ignore */ }
            });
        });

        /* Keep the active item in view in a long sidebar. */
        var current = document.querySelector('.sidebar__items [aria-current="page"]');
        if (current && current.scrollIntoView) {
            current.scrollIntoView({ block: 'nearest' });
        }
    });
})();
