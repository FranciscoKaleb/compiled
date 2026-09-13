"""Object tracking: single-object, multi-object and optical flow.

The browser sends frames from its own webcam; the server keeps per-session
tracker state. page25 and page26 each had their own copy of the session store
and the encode/decode helpers — there is now one of each.
"""
import os
import secrets
import tempfile
import threading
import time

import numpy as np
from flask import request

from app.blueprints.models._base import bp, predictor
from app.core.errors import AppError
from app.core.imaging import from_b64_frame, to_b64_jpeg
from app.core.responses import ok
from app.core.uploads import VIDEO_EXTENSIONS, get_file

MAX_SESSIONS = 20
SESSION_TTL = 300          # five idle minutes
TRACK_COLOR = (0, 220, 80)

_sessions: dict[str, dict] = {}
_lock = threading.Lock()


def _purge():
    cutoff = time.time() - SESSION_TTL
    with _lock:
        for key in [k for k, v in _sessions.items() if v['ts'] < cutoff]:
            del _sessions[key]


def _open_session(**state) -> str:
    _purge()
    session_id = secrets.token_urlsafe(12)
    with _lock:
        if len(_sessions) >= MAX_SESSIONS:
            oldest = min(_sessions, key=lambda k: _sessions[k]['ts'])
            del _sessions[oldest]
        _sessions[session_id] = {**state, 'ts': time.time()}
    return session_id


def _get_session(session_id: str) -> dict:
    with _lock:
        entry = _sessions.get(session_id)
    if entry is None:
        raise AppError('That tracking session expired — click Start again.')
    entry['ts'] = time.time()
    return entry


def _frame_from(payload, key='frame'):
    frame = from_b64_frame(payload.get(key, ''))
    if frame is None:
        raise AppError('Could not decode the video frame.')
    return frame


def _payload():
    return request.get_json(silent=True) or {}


# ---------------------------------------------------------------------------
# Single object tracking
# ---------------------------------------------------------------------------

def _make_tracker():
    """CSRT where available, MIL as a fallback.

    The old page advertised CSRT in its title, route name and docs but
    constructed a MIL tracker, which is markedly less accurate.
    """
    import cv2

    for factory in ('TrackerCSRT_create', 'legacy.TrackerCSRT_create'):
        target = cv2
        try:
            for part in factory.split('.'):
                target = getattr(target, part)
            return target(), 'CSRT'
        except AttributeError:
            continue
    return cv2.TrackerMIL_create(), 'MIL'


@bp.post('/track/single/init')
def track_single_init():
    import cv2

    payload = _payload()
    try:
        x, y, w, h = (int(payload[k]) for k in ('x', 'y', 'w', 'h'))
    except (KeyError, TypeError, ValueError):
        raise AppError('Draw a box on the video to pick a target.')
    if w < 5 or h < 5:
        raise AppError('That box is too small — drag a larger one.')

    frame = _frame_from(payload)
    tracker, algorithm = _make_tracker()
    tracker.init(frame, (x, y, w, h))
    session_id = _open_session(tracker=tracker, algorithm=algorithm)

    preview = frame.copy()
    cv2.rectangle(preview, (x, y), (x + w, y + h), TRACK_COLOR, 2)
    cv2.putText(preview, 'Target', (x, max(y - 8, 14)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, TRACK_COLOR, 2)

    return ok(session_id=session_id, algorithm=algorithm, frame=to_b64_jpeg(preview))


@bp.post('/track/single/update')
def track_single_update():
    import cv2

    payload = _payload()
    entry = _get_session(payload.get('session_id', ''))
    frame = _frame_from(payload)

    found, bbox = entry['tracker'].update(frame)
    if found:
        x, y, w, h = (int(v) for v in bbox)
        cv2.rectangle(frame, (x, y), (x + w, y + h), TRACK_COLOR, 2)
        cv2.putText(frame, 'Tracking', (x, max(y - 8, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, TRACK_COLOR, 2)
    else:
        cv2.putText(frame, 'Target lost', (10, 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (30, 30, 220), 2)

    return ok(frame=to_b64_jpeg(frame), tracking=bool(found))


# ---------------------------------------------------------------------------
# Multi object tracking: background subtraction + SORT-style association
# ---------------------------------------------------------------------------

_PALETTE = [
    (220, 80, 0), (0, 160, 220), (180, 0, 210), (0, 210, 160),
    (210, 180, 0), (210, 0, 100), (80, 210, 0), (0, 80, 220),
    (150, 80, 220), (220, 120, 0), (0, 220, 80), (80, 0, 220),
]


def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    union = ((a[2] - a[0]) * (a[3] - a[1])
             + (b[2] - b[0]) * (b[3] - b[1]) - intersection)
    return intersection / (union + 1e-6)


def _greedy(cost):
    """Fallback association when scipy is unavailable."""
    rows, cols, taken = [], [], set()
    for row in range(cost.shape[0]):
        best = min(
            (c for c in range(cost.shape[1]) if c not in taken),
            key=lambda c: cost[row, c], default=None,
        )
        if best is not None:
            rows.append(row)
            cols.append(best)
            taken.add(best)
    return rows, cols


class Sort:
    """Minimal SORT: IoU association, ids survive two missed frames."""

    MAX_MISSES = 2
    MIN_IOU = 0.25

    def __init__(self):
        self.tracks: list[dict] = []
        self._next_id = 1

    def _spawn(self, bbox) -> dict:
        track = {'id': self._next_id, 'bbox': bbox, 'miss': 0}
        self._next_id += 1
        return track

    def update(self, detections) -> list[dict]:
        if not self.tracks:
            self.tracks = [self._spawn(d) for d in detections]
            return list(self.tracks)

        if not detections:
            self.tracks = [
                dict(t, miss=t['miss'] + 1)
                for t in self.tracks if t['miss'] < self.MAX_MISSES
            ]
            return list(self.tracks)

        cost = np.array([[-_iou(t['bbox'], d) for d in detections] for t in self.tracks])
        try:
            from scipy.optimize import linear_sum_assignment
            rows, cols = linear_sum_assignment(cost)
        except ImportError:
            rows, cols = _greedy(cost)

        matched_tracks, matched_dets, updated = set(), set(), []
        for row, col in zip(rows, cols):
            if -cost[row, col] >= self.MIN_IOU:
                updated.append({'id': self.tracks[row]['id'], 'bbox': detections[col], 'miss': 0})
                matched_tracks.add(row)
                matched_dets.add(col)

        updated.extend(
            dict(t, miss=t['miss'] + 1)
            for i, t in enumerate(self.tracks)
            if i not in matched_tracks and t['miss'] < self.MAX_MISSES
        )
        updated.extend(
            self._spawn(d) for j, d in enumerate(detections) if j not in matched_dets
        )

        self.tracks = updated
        return list(self.tracks)


@bp.post('/track/multi/init')
def track_multi_init():
    import cv2

    payload = _payload()
    min_area = max(100, int(payload.get('min_area', 500)))
    session_id = _open_session(
        bg=cv2.createBackgroundSubtractorMOG2(history=30, varThreshold=25, detectShadows=False),
        sort=Sort(),
        min_area=min_area,
    )
    return ok(session_id=session_id)


@bp.post('/track/multi/update')
def track_multi_update():
    import cv2

    payload = _payload()
    entry = _get_session(payload.get('session_id', ''))
    frame = _frame_from(payload)

    if 'min_area' in payload:
        entry['min_area'] = max(100, int(payload['min_area']))

    mask = entry['bg'].apply(frame)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detections = []
    for contour in contours:
        if cv2.contourArea(contour) >= entry['min_area']:
            x, y, w, h = cv2.boundingRect(contour)
            detections.append([x, y, x + w, y + h])

    live = [t for t in entry['sort'].update(detections) if t['miss'] == 0]
    for track in live:
        x1, y1, x2, y2 = (int(v) for v in track['bbox'])
        color = _PALETTE[track['id'] % len(_PALETTE)]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, f'ID {track["id"]}', (x1, max(y1 - 6, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    cv2.putText(frame, f'Active: {len(live)}', (8, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    return ok(
        frame=to_b64_jpeg(frame),
        active=len(live),
        unique_ids=entry['sort']._next_id - 1,
    )


@bp.post('/track/<any(single, multi):mode>/stop')
def track_stop(mode):
    session_id = _payload().get('session_id')
    with _lock:
        _sessions.pop(session_id, None)
    return ok()


# ---------------------------------------------------------------------------
# Optical flow over an uploaded video
# ---------------------------------------------------------------------------

MAX_FRAMES = 180
MAX_DIM = 800


@predictor('track', 'flow')
def flow(spec):
    import cv2

    upload = get_file('video', allowed=VIDEO_EXTENSIONS)
    suffix = os.path.splitext(upload.filename)[1] or '.mp4'

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        upload.save(tmp.name)
        path = tmp.name

    capture = None
    try:
        capture = cv2.VideoCapture(path)
        if not capture.isOpened():
            raise AppError('Could not open that video — try MP4 or AVI.')

        fps = capture.get(cv2.CAP_PROP_FPS) or 25
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

        read, previous = capture.read()
        if not read:
            raise AppError('That video appears to be empty.')

        previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
        corner_params = dict(maxCorners=200, qualityLevel=0.3, minDistance=7, blockSize=7)
        lk_params = dict(
            winSize=(15, 15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03),
        )

        points = cv2.goodFeaturesToTrack(previous_gray, mask=None, **corner_params)
        colors = np.random.default_rng(42).integers(60, 255, size=(500, 3)).tolist()

        scale = min(1.0, MAX_DIM / max(width, height, 1))
        target = (max(1, int(width * scale)), max(1, int(height * scale)))
        trails = np.zeros_like(previous)

        def encode(frame):
            if scale < 1.0:
                frame = cv2.resize(frame, target)
            return to_b64_jpeg(frame)

        frames = [encode(previous)]
        while len(frames) < MAX_FRAMES:
            read, frame = capture.read()
            if not read:
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if points is None or len(points) == 0:
                frames.append(encode(frame))
                previous_gray = gray.copy()
                continue

            moved, status, _ = cv2.calcOpticalFlowPyrLK(
                previous_gray, gray, points, None, **lk_params
            )
            if moved is None:
                frames.append(encode(frame))
                previous_gray = gray.copy()
                continue

            good_new, good_old = moved[status == 1], points[status == 1]
            for index, (new, old) in enumerate(zip(good_new, good_old)):
                a, b = new.ravel().astype(int)
                c, d = old.ravel().astype(int)
                color = colors[index % len(colors)]
                trails = cv2.line(trails, (a, b), (c, d), color, 2)
                frame = cv2.circle(frame, (a, b), 3, color, -1)

            composite = cv2.add(frame, trails)
            cv2.putText(composite, f'Points: {len(good_new)}', (8, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            frames.append(encode(composite))

            previous_gray = gray.copy()
            points = good_new.reshape(-1, 1, 2)

            # Re-seed once the flow has lost most of its features.
            if len(points) < 20:
                fresh = cv2.goodFeaturesToTrack(previous_gray, mask=None, **corner_params)
                if fresh is not None:
                    points = np.vstack([points, fresh]) if len(points) else fresh
                trails = np.zeros_like(previous)

        return ok(frames=frames, fps=round(min(fps, 30)), count=len(frames))
    finally:
        if capture is not None:
            capture.release()
        if os.path.exists(path):
            os.unlink(path)
