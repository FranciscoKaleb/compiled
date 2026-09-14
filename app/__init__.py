"""Application factory."""
from flask import Flask, redirect

from app.config import Config
from app.core import errors, loader
from app.extensions import db, migrate
from app.chain_catalog import CHAINS
from app.lab_catalog import labs_by_group
from app.registry import (
    CATEGORY_TITLES, MODELS, TOOLS, legacy_redirects, models_by_category,
    tools_by_category,
)


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    config_object.ensure_dirs()

    db.init_app(app)
    if migrate is not None:
        migrate.init_app(app, db)

    loader.configure(app.config['MODELS_DIR'])

    # Imported for their side effect of registering routes on the blueprints.
    from app.blueprints import chain, lab, main, models, tools

    app.register_blueprint(main.bp)
    app.register_blueprint(models.bp)
    app.register_blueprint(tools.bp)
    app.register_blueprint(lab.bp)
    app.register_blueprint(chain.bp)
    _register_websockets(app)

    errors.register(app)
    _register_redirects(app)
    _register_template_globals(app)

    from app import cli
    cli.register(app)

    # Imported so Flask-Migrate can see the tables.
    from app.db import models as _db_models  # noqa: F401

    return app


def _register_websockets(app: Flask) -> None:
    """WebSocket routes via flask-sock; the lab runs without it, minus that demo."""
    try:
        from flask_sock import Sock
    except ImportError:
        app.config['WEBSOCKETS_AVAILABLE'] = False
        return
    sock = Sock(app)
    from app.blueprints.lab import browser, realtime
    realtime.register_websocket(sock)
    browser.register_websocket(sock)
    app.config['WEBSOCKETS_AVAILABLE'] = True


def _register_redirects(app: Flask) -> None:
    """301 every retired URL at its replacement, so old links keep working."""
    for index, (old, new) in enumerate(legacy_redirects()):
        app.add_url_rule(
            old,
            endpoint=f'legacy_{index}',
            view_func=lambda new=new: redirect(new, code=301),
        )


def _register_template_globals(app: Flask) -> None:
    @app.context_processor
    def inject():
        return {
            'all_models': MODELS,
            'all_tools': TOOLS,
            'categories': models_by_category(),
            'tool_categories': tools_by_category(),
            'lab_groups': labs_by_group(),
            'chains': CHAINS,
            'category_titles': CATEGORY_TITLES,
        }
