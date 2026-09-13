"""Flask extensions, instantiated unbound so `create_app` can attach them."""
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)

try:
    from flask_migrate import Migrate

    migrate = Migrate()
except ImportError:  # pragma: no cover - Flask-Migrate is optional at runtime
    migrate = None
