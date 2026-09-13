"""The tools blueprint plus handler registration."""
from flask import Blueprint

bp = Blueprint('tools', __name__, url_prefix='/tools')

# slug -> handler(spec) -> response
RUNNERS = {}


def runner(slug: str):
    """Mark a function as the POST /tools/<slug>/run handler."""
    def decorator(fn):
        RUNNERS[slug] = fn
        return fn
    return decorator
