"""Web Lab routes: pages from the catalogue plus the demo APIs."""
from flask import Blueprint, render_template

from app.lab_catalog import LABS, labs_by_group

bp = Blueprint('lab', __name__, url_prefix='/lab')


@bp.get('/')
def catalog():
    return render_template('lab/catalog.html', groups=labs_by_group(), active='catalog')


def _page_view(spec):
    def view():
        return render_template(spec.template, spec=spec, active=spec.slug)
    view.__name__ = spec.slug.replace('-', '_')
    return view


def register():
    from app.blueprints.lab import auth, basics, browser, data, http, oauth, realtime, server  # noqa: F401  (add API routes to bp)

    for spec in LABS:
        bp.add_url_rule(f'/{spec.slug}', endpoint=spec.slug.replace('-', '_'), view_func=_page_view(spec))


register()


@bp.get('/csrf/attacker', endpoint='csrf_attacker')
def csrf_attacker():
    return render_template('lab/csrf_attacker.html')
