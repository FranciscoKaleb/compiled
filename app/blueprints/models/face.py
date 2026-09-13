"""Face analysis: detection, 1:1 comparison, 1:N identification, live streams.

The five InsightFace pages used to be five files with three copies of the
detector setup — two of which bypassed the model cache entirely and pulled a
second copy of the weights out of ~/.insightface. They now share one cached
analyzer and one matching implementation.
"""
import numpy as np
from flask import Response, current_app, request, stream_with_context

from app.blueprints.models._base import bp, predictor
from app.core import loader
from app.core.errors import AppError, BadUpload
from app.core.imaging import draw_boxes, to_b64_png
from app.core.responses import fail, ok
from app.core.uploads import decode_data_url, read_image
from app.db import faces
from app.registry import BY_SLUG

ANALYZER_SLUG = 'face/detect'


def _analyzer():
    return loader.get(ANALYZER_SLUG).model


def _faces_in(image):
    """Detected faces, largest first — so "the" face is the closest one."""
    found = _analyzer().get(np.array(image))
    return sorted(found, key=lambda f: -_area(f.bbox))


def _area(bbox) -> float:
    return float((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))


# ---------------------------------------------------------------------------
# Still images
# ---------------------------------------------------------------------------

@predictor('face', 'detect')
def detect(spec):
    image = read_image()
    found = _faces_in(image)

    boxes = [face.bbox.tolist() for face in found]
    captions = []
    for face in found:
        bits = []
        age = getattr(face, 'age', None)
        sex = getattr(face, 'sex', None)
        if sex:
            bits.append(str(sex))
        if age is not None:
            bits.append(f'~{int(age)}')
        captions.append(' '.join(bits) or 'face')

    annotated = draw_boxes(image, boxes, captions, width=3)
    count = len(found)
    return ok(
        image_data=to_b64_png(annotated),
        detections=[{'label': caption, 'score': 1.0} for caption in captions],
        summary=f'Found {count} face(s)' if count else 'No faces found',
    )


@predictor('face', 'compare')
def compare(spec):
    """1:1 verification.

    The old handler assigned `similarity` only on the success branch and then
    unconditionally called float(similarity) — so every "no face detected"
    request raised UnboundLocalError and returned a 500.
    """
    first, second = read_image('image1'), read_image('image2')

    faces_a, faces_b = _faces_in(first), _faces_in(second)
    if not faces_a or not faces_b:
        missing = []
        if not faces_a:
            missing.append('the first')
        if not faces_b:
            missing.append('the second')
        raise AppError(f'No face detected in {" and ".join(missing)} image.')

    a = faces.FaceEmbedding.normalise(faces_a[0].embedding)
    b = faces.FaceEmbedding.normalise(faces_b[0].embedding)
    similarity = float(np.dot(a, b))

    threshold = current_app.config['FACE_COMPARE_THRESHOLD']
    same = similarity > threshold
    return ok(
        similarity=similarity,
        threshold=threshold,
        same=same,
        verdict='Same person' if same else 'Different people',
        summary=f'Cosine similarity {similarity:.3f} (threshold {threshold:.2f})',
    )


# ---------------------------------------------------------------------------
# Enrolment and identification (database-backed)
# ---------------------------------------------------------------------------

def _embedding_from_request(field='image'):
    """Accept either a multipart upload or a base64 data URL from a canvas."""
    if request.files.get(field):
        image = read_image(field)
    else:
        payload = request.get_json(silent=True) or {}
        image = decode_data_url(payload.get(field), field=field)

    found = _faces_in(image)
    if not found:
        raise AppError('No face detected — move closer to the camera and retry.')
    return found[0].embedding


@bp.post('/face/identify/enroll')
def enroll():
    payload = request.get_json(silent=True) or {}
    name = (payload.get('name') or request.form.get('name') or '').strip()

    if not name:
        raise AppError('Enter a name to enrol this face under.')
    if len(name) > 255:
        raise AppError('That name is too long (255 characters maximum).')

    embedding = _embedding_from_request()
    person = faces.enrol(name, embedding)
    samples = len(person.embeddings)

    return ok(
        name=person.name,
        person_id=person.id,
        samples=samples,
        message=f'Enrolled {person.name} ({samples} sample(s) on file).',
    )


@bp.post('/face/identify/match')
def match():
    embedding = _embedding_from_request()
    threshold = current_app.config['FACE_MATCH_THRESHOLD']
    person_id, name, similarity = faces.identify(embedding, threshold, source='still')

    if name is None:
        return ok(
            matched=False, similarity=similarity,
            message='No match found. Enrol this face first.' if similarity == 0.0
                    else f'No match — closest was {similarity:.2f}, below {threshold:.2f}.',
        )
    return ok(
        matched=True, name=name, person_id=person_id, similarity=similarity,
        message=f'Welcome {name} — similarity {similarity:.2f}.',
    )


@bp.get('/face/identify/roster')
def roster():
    return ok(people=faces.roster())


@bp.delete('/face/identify/roster/<int:person_id>')
def forget(person_id):
    if not faces.forget(person_id):
        return fail('That person is no longer enrolled.', 404)
    return ok(message='Removed.')


@predictor('face', 'identify')
def identify(spec):
    """The page's own predict endpoint is the match endpoint."""
    return match()


# ---------------------------------------------------------------------------
# Live MJPEG streams off the server's camera
# ---------------------------------------------------------------------------

def _camera(index: int = 0):
    import cv2

    camera = cv2.VideoCapture(index)
    if not camera.isOpened():
        camera.release()
        raise AppError('No camera available on the machine running this app.', 503)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    camera.set(cv2.CAP_PROP_FPS, 24)
    return camera


def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    union = _area(a) + _area(b) - intersection
    return intersection / union if union > 0 else 0.0


def _stream(recognise: bool, threshold: float):
    """Yield MJPEG parts. The camera is always released, even on disconnect."""
    import cv2

    camera = _camera()
    tracked: dict[tuple, dict] = {}
    frame_index = 0

    try:
        while True:
            success, frame = camera.read()
            if not success:
                break
            frame_index += 1

            # Detection is the expensive part: run it on every Nth frame and
            # redraw the last known boxes in between.
            interval = 10 if recognise else 2
            if frame_index % interval == 0:
                detected = _analyzer().get(frame)
                refreshed: dict[tuple, dict] = {}

                for face in detected:
                    bbox = face.bbox.astype(int)
                    key = tuple(bbox)
                    label = 'face'

                    if recognise:
                        # Reuse a confirmed identity for a box that barely
                        # moved, so labels stop flickering between frames.
                        carried = next(
                            (data for old, data in tracked.items() if _iou(bbox, old) > 0.5),
                            None,
                        )
                        if carried and carried['confirmed']:
                            refreshed[key] = carried
                            continue

                        _, name, _ = faces.identify(
                            face.embedding, threshold, source='webcam', log=False
                        )
                        name = name or 'Unknown'

                        if carried and carried['name'] == name:
                            carried['hits'] += 1
                            carried['confirmed'] = carried['hits'] >= 2
                            refreshed[key] = carried
                        else:
                            refreshed[key] = {'name': name, 'hits': 1, 'confirmed': False}
                        continue

                    refreshed[key] = {'name': label, 'hits': 1, 'confirmed': True}

                tracked = refreshed

            for bbox, data in tracked.items():
                cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 220, 80), 2)
                if recognise:
                    cv2.putText(
                        frame, data['name'], (bbox[0], max(bbox[1] - 10, 16)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 80), 2,
                    )

            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                   + buffer.tobytes() + b'\r\n')
    finally:
        camera.release()


def _stream_response(recognise: bool):
    threshold = current_app.config['FACE_MATCH_THRESHOLD']
    if recognise:
        faces.invalidate()          # pick up anyone enrolled since last time
    return Response(
        stream_with_context(_stream(recognise, threshold)),
        mimetype='multipart/x-mixed-replace; boundary=frame',
    )


@bp.get('/face/live-detect/stream')
def live_detect_stream():
    return _stream_response(recognise=False)


@bp.get('/face/live-identify/stream')
def live_identify_stream():
    return _stream_response(recognise=True)
