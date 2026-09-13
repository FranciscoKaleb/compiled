"""Tool routes, generated from the catalogue.

Every tool gets GET /tools/<slug> (its page), POST /tools/<slug>/run, and the
shared download/preview routes. Handler modules only write the run function.
"""
from flask import render_template, send_file

from app.blueprints.tools._base import RUNNERS, bp, runner  # noqa: F401
from app.core import storage, toolkit
from app.registry import TOOLS, TOOLS_BY_SLUG


def _page_view(spec):
    def view():
        template = spec.template or 'tools/run.html'
        return render_template(template, spec=spec, active=spec.slug)
    view.__name__ = spec.view
    return view


def _run_view(spec, handler):
    def view():
        if spec.needs:
            toolkit.require(*spec.needs)
        return handler(spec)
    view.__name__ = spec.view + '_run'
    return view


@bp.get('/<slug>/download/<job_id>/<name>')
def download(slug, job_id, name):
    if slug not in TOOLS_BY_SLUG:
        from flask import abort
        abort(404)
    path = storage.job_file(slug, job_id, name)
    return send_file(path, as_attachment=True, download_name=name)


@bp.get('/<slug>/preview/<job_id>/<name>')
def preview(slug, job_id, name):
    if slug not in TOOLS_BY_SLUG:
        from flask import abort
        abort(404)
    path = storage.job_file(slug, job_id, name)
    return send_file(path, conditional=True)      # Range support for <video>


def register():
    from app.blueprints.tools import (  # noqa: F401
        data, documents, image, metadata_remover, pdf, video,
        video_metadata_remover,
    )

    for spec in TOOLS:
        bp.add_url_rule(f'/{spec.slug}', endpoint=spec.view, view_func=_page_view(spec))
        handler = RUNNERS.get(spec.slug)
        if handler is not None:
            bp.add_url_rule(f'/{spec.slug}/run', endpoint=spec.view + '_run',
                            view_func=_run_view(spec, handler), methods=['POST'])


register()
