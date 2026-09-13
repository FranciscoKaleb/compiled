"""Shared error types and the handlers that turn them into responses."""
from flask import jsonify, render_template, request


class AppError(Exception):
    """An error we can show the user verbatim. Never leaks internals."""

    status = 400

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        if status is not None:
            self.status = status


class BadUpload(AppError):
    """The uploaded file was missing, the wrong type, or unreadable."""


def wants_json() -> bool:
    """True when the caller is fetch()-ing an endpoint rather than a page."""
    if request.accept_mimetypes.best == 'application/json':
        return True
    if request.is_json or request.method == 'POST':
        return True
    return request.path.rsplit('/', 1)[-1] in {
        'predict', 'init', 'update', 'stop', 'upload', 'enroll', 'match', 'run'
    }


def register(app):
    @app.errorhandler(AppError)
    def _app_error(exc: AppError):
        if wants_json():
            return jsonify({'ok': False, 'error': exc.message}), exc.status
        return render_template('error.html', code=exc.status, message=exc.message), exc.status

    @app.errorhandler(400)
    def _bad_request(exc):
        message = 'The request was malformed or a required field was missing.'
        if wants_json():
            return jsonify({'ok': False, 'error': message}), 400
        return render_template('error.html', code=400, message=message), 400

    @app.errorhandler(404)
    def _not_found(exc):
        message = 'That page does not exist.'
        if wants_json():
            return jsonify({'ok': False, 'error': message}), 404
        return render_template('error.html', code=404, message=message), 404

    @app.errorhandler(413)
    def _too_large(exc):
        limit = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
        message = f'File too large — the maximum upload size is {limit} MB.'
        if wants_json():
            return jsonify({'ok': False, 'error': message}), 413
        return render_template('error.html', code=413, message=message), 413

    @app.errorhandler(500)
    def _server_error(exc):
        app.logger.exception('unhandled error at %s', request.path)
        message = 'Something went wrong on the server. Check the server log.'
        if wants_json():
            return jsonify({'ok': False, 'error': message}), 500
        return render_template('error.html', code=500, message=message), 500
