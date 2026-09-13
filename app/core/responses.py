"""One response envelope for every JSON endpoint.

The old code had three ad-hoc shapes ({'predictions'}, {'detections',
'image_data'}, {'image_data', 'face_count', 'message'}) plus two pages that
returned rendered HTML. runner.js only has to understand this one.
"""
from flask import jsonify


def ok(**data):
    return jsonify({'ok': True, **data})


def fail(message: str, status: int = 400):
    return jsonify({'ok': False, 'error': message}), status
