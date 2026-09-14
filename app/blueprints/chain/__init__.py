"""Blockchain section: pages from the catalogue, APIs from the three chain modules."""
from flask import Blueprint, render_template

from app.chain_catalog import CHAINS

bp = Blueprint('chain', __name__, url_prefix='/blockchain')


@bp.get('/', endpoint='catalog')
def catalog():
    return render_template('chain/catalog.html', chains=CHAINS, active='catalog')


def _page(spec):
    def view():
        return render_template(spec.template, spec=spec, chains=CHAINS, active=spec.slug)
    view.__name__ = 'page_' + spec.slug
    return view


def register():
    from app.blueprints.chain import coin, ledger, permissioned  # noqa: F401  (add API routes to bp)
    for spec in CHAINS:
        bp.add_url_rule(f'/{spec.slug}', endpoint=spec.slug, view_func=_page(spec))


register()
