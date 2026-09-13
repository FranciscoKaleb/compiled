"""Model routes, generated from the registry.

Every page gets `GET /models/<slug>`; every spec with a registered predictor
also gets `POST /models/<slug>/predict`. Pages with their own interaction
(enrolment, live streams, frame-by-frame tracking) add routes in their module.
"""
from flask import render_template

from app.blueprints.models._base import PREDICTORS, bp, predictor  # noqa: F401
from app.registry import MODELS

# Pages whose interaction is too specific for the generic runner template.
CUSTOM_TEMPLATES = {
    'face/identify': 'models/face_identify.html',
    'face/live-detect': 'models/face_live.html',
    'face/live-identify': 'models/face_live.html',
    'track/single': 'models/track_single.html',
    'track/multi': 'models/track_multi.html',
    'track/flow': 'models/track_flow.html',
}


def template_for(spec) -> str:
    return CUSTOM_TEMPLATES.get(spec.slug, 'models/run.html')


def _page_view(spec):
    def view():
        return render_template(template_for(spec), spec=spec, active=spec.slug)
    view.__name__ = spec.endpoint.split('.', 1)[1]
    return view


def _predict_view(spec, handler):
    def view():
        return handler(spec)
    view.__name__ = spec.endpoint.split('.', 1)[1] + '_predict'
    return view


def register():
    """Wire every registry entry onto the blueprint. Called once at import."""
    # Importing the handler modules populates PREDICTORS and adds their own
    # routes, so it has to happen before the loop below.
    from app.blueprints.models import (  # noqa: F401
        classify, detect, face, ocr, segment, text, track,
    )

    for spec in MODELS:
        name = spec.endpoint.split('.', 1)[1]
        bp.add_url_rule(f'/{spec.slug}', endpoint=name, view_func=_page_view(spec))

        handler = PREDICTORS.get((spec.category, spec.view))
        if handler is not None:
            bp.add_url_rule(
                f'/{spec.slug}/predict',
                endpoint=f'{name}_predict',
                view_func=_predict_view(spec, handler),
                methods=['POST'],
            )


register()
