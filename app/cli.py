"""Command line helpers: `flask --app run <command>`."""
import click
from flask.cli import with_appcontext

from app.extensions import db


def register(app):
    app.cli.add_command(init_db)
    app.cli.add_command(faces_cmd)
    app.cli.add_command(routes_smoke)


@click.command('init-db')
@with_appcontext
def init_db():
    """Create every table directly, without Alembic.

    A fallback for when Flask-Migrate is not installed; `flask db upgrade` is
    the normal path.
    """
    from app.db import models  # noqa: F401

    db.create_all()
    click.echo('Tables created.')


@click.group('faces')
def faces_cmd():
    """Inspect and edit the enrolled faces."""


@faces_cmd.command('list')
@with_appcontext
def faces_list():
    from app.db import faces

    people = faces.roster()
    if not people:
        click.echo('Nobody is enrolled yet.')
        return
    for person in people:
        click.echo(f'{person["id"]:>4}  {person["name"]:<30} '
                   f'{person["samples"]} sample(s)  {person["enrolled_at"][:19]}')


@faces_cmd.command('forget')
@click.argument('person_id', type=int)
@with_appcontext
def faces_forget(person_id):
    from app.db import faces

    click.echo('Removed.' if faces.forget(person_id) else 'No such person.')


@click.command('routes-smoke')
@with_appcontext
def routes_smoke():
    """GET every argument-free route and report the status of each.

    Pages must return 200/301/302; API endpoints must not 5xx.

    Catches missing templates and broken url_for calls across the whole app in
    one run, which is how the old tools/home.html stayed broken unnoticed.
    """
    from flask import current_app

    client = current_app.test_client()
    # Streams and downloads are excluded: they either block or need a job id.
    skip = {'static', 'main.cache_status'}

    failures = 0
    checked = 0
    for rule in sorted(current_app.url_map.iter_rules(), key=lambda r: str(r)):
        if rule.arguments or rule.endpoint in skip:
            continue
        if 'GET' not in rule.methods or '/stream' in str(rule) or getattr(rule, 'websocket', False):
            continue
        if str(rule).endswith('/ws'):          # websocket upgrade endpoints reject plain GETs
            continue

        checked += 1
        response = client.get(str(rule), follow_redirects=False)
        path = str(rule)
        # Pages must render. API-style endpoints may legitimately refuse an
        # anonymous, parameterless GET (401/400) — only a 5xx is a bug there.
        is_api = '/api/' in path or '/idp/' in path
        good = response.status_code < 500 if is_api else response.status_code in (200, 301, 302)
        if not good:
            failures += 1
            click.echo(f'  FAIL {response.status_code}  {rule}')

    click.echo(f'{checked - failures}/{checked} routes OK')
    if failures:
        raise SystemExit(1)
