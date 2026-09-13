"""Handler registration shared by the model modules."""
from flask import Blueprint

bp = Blueprint('models', __name__, url_prefix='/models')

# (category, view) -> handler(spec) -> response
PREDICTORS = {}


def predictor(category: str, view: str):
    """Mark a function as the POST handler for specs with this category/view."""
    def decorator(fn):
        PREDICTORS[(category, view)] = fn
        return fn
    return decorator
