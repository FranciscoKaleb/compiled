"""Home page, catalogues and the model-cache controls."""
from flask import Blueprint, render_template

from app.core import loader
from app.core.responses import ok
from app.registry import MODELS, TOOLS, models_by_category

bp = Blueprint('main', __name__)


@bp.get('/')
def home():
    return render_template(
        'home.html',
        model_count=len(MODELS),
        tool_count=len(TOOLS),
        categories=models_by_category(),
        tools=TOOLS,
    )


@bp.get('/models')
def models_catalog():
    return render_template(
        'models/catalog.html', categories=models_by_category(), active='catalog'
    )


@bp.get('/tools')
def tools_catalog():
    return render_template('tools/catalog.html', tools=TOOLS, active='catalog')


@bp.get('/models/cache')
def cache_status():
    return ok(loaded=loader.loaded_keys())


@bp.post('/models/cache/clear')
def cache_clear():
    freed = loader.clear()
    return ok(freed=freed, count=len(freed))


@bp.post('/models/cache/unload/<path:slug>')
def cache_unload(slug):
    return ok(removed=loader.unload(slug))
