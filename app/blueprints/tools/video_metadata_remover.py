"""Video metadata remover.

Reads every tag ffprobe can see — container tags, per-stream tags, chapters —
and writes a copy with all of it dropped. The streams are copied, not
re-encoded, so the picture and sound are untouched and even long files finish
in seconds.

Needs the ffmpeg and ffprobe binaries on PATH.
"""
import json
import re
import shutil
import subprocess

from flask import request

from app.blueprints.tools._base import bp
from app.core import storage
from app.core.errors import AppError
from app.core.responses import ok
from app.core.uploads import VIDEO_EXTENSIONS, extension_of, get_file

TOOL = 'video-metadata-remover'
FFMPEG_TIMEOUT = 600          # seconds; stream copy of a 500 MB file is well under this

# Tag keys (lower-cased, matched as substrings) that identify a person, a
# device, a time or a place.
SENSITIVE_HINTS = (
    'location', 'gps', 'latitude', 'longitude', 'iso6709',
    'creation_time', 'date', 'make', 'model', 'software', 'encoder',
    'artist', 'author', 'comment', 'copyright', 'description', 'title',
    'com.apple', 'com.android', 'device', 'serial', 'owner',
)

# Keys every muxer writes to describe the container itself. They are shown but
# not counted, so "0 remaining" means what people expect it to mean.
STRUCTURAL = {'major_brand', 'minor_version', 'compatible_brands', 'vendor_id',
              'language', 'handler_name'}

# ISO 6709 as written by phones:  +14.5833+121.0000/  or  +14.5833+121.0000+12.3/
_ISO6709 = re.compile(r'^([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)(?:([+-]\d+(?:\.\d+)?))?/?$')


def _require_binaries():
    if not (shutil.which('ffprobe') and shutil.which('ffmpeg')):
        raise AppError('ffmpeg is not installed on the machine running this app.', 503)


def _sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(hint in lowered for hint in SENSITIVE_HINTS)


def _location_from(tags: dict) -> str | None:
    """Decimal lat/long from any of the keys phones use."""
    for key, value in tags.items():
        if 'location' not in key.lower() and 'iso6709' not in key.lower():
            continue
        match = _ISO6709.match(str(value).strip())
        if match:
            return f'{float(match.group(1)):.6f}, {float(match.group(2)):.6f}'
    return None


def probe(path) -> dict:
    """ffprobe's view of the file as a dict; raises AppError on failure."""
    try:
        completed = subprocess.run(
            ['ffprobe', '-v', 'error', '-print_format', 'json',
             '-show_format', '-show_streams', '-show_chapters', str(path)],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except subprocess.TimeoutExpired:
        raise AppError('Reading the video took too long.')
    if completed.returncode != 0 or not completed.stdout:
        raise AppError('Could not read that file as a video.')
    return json.loads(completed.stdout)


def inspect(info: dict) -> dict:
    """Group everything ffprobe reported, flagging the personal bits."""
    groups = []
    fmt = info.get('format', {})
    streams = info.get('streams', [])
    chapters = info.get('chapters', [])

    basics = [
        {'tag': 'Container', 'value': fmt.get('format_long_name') or fmt.get('format_name', '?'),
         'sensitive': False},
        {'tag': 'Duration', 'value': _duration(fmt.get('duration')), 'sensitive': False},
        {'tag': 'Streams', 'value': ', '.join(
            f"{s.get('codec_type', '?')} ({s.get('codec_name', '?')})" for s in streams
        ) or 'none', 'sensitive': False},
    ]
    groups.append({'title': 'File', 'rows': basics})

    format_tags = fmt.get('tags') or {}
    location = _location_from(format_tags)
    if format_tags:
        rows = [
            {'tag': key, 'value': _short(value), 'sensitive': _sensitive(key)}
            for key, value in format_tags.items()
        ]
        rows.sort(key=lambda row: (not row['sensitive'], row['tag'].lower()))
        groups.append({'title': 'Container tags', 'rows': rows})

    for stream in streams:
        tags = stream.get('tags') or {}
        location = location or _location_from(tags)
        rows = [
            {'tag': key, 'value': _short(value), 'sensitive': _sensitive(key)}
            for key, value in tags.items()
        ]
        # Rotation and other side data are shown so people know what stays.
        for side in stream.get('side_data_list') or []:
            if 'rotation' in side:
                rows.append({'tag': 'rotation (display matrix)', 'value': str(side['rotation']),
                             'sensitive': False})
        if rows:
            rows.sort(key=lambda row: (not row['sensitive'], row['tag'].lower()))
            label = f"{stream.get('codec_type', 'stream').title()} stream #{stream.get('index', '?')}"
            groups.append({'title': label, 'rows': rows})

    if chapters:
        rows = [
            {'tag': f"Chapter {i + 1}",
             'value': (chapter.get('tags') or {}).get('title', '(untitled)'),
             'sensitive': False}
            for i, chapter in enumerate(chapters)
        ]
        groups.append({'title': 'Chapters', 'rows': rows})

    count = sum(
        1 for group in groups[1:] for row in group['rows']
        if row['tag'].lower() not in STRUCTURAL
        and not row['tag'].startswith('rotation')
    )
    return {'groups': groups, 'count': count, 'location': location}


def _short(value) -> str:
    text = str(value).strip()
    return text[:180] + '…' if len(text) > 180 else text


def _duration(seconds) -> str:
    try:
        total = float(seconds)
    except (TypeError, ValueError):
        return 'unknown'
    minutes, secs = divmod(int(round(total)), 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours}:{minutes:02d}:{secs:02d}' if hours else f'{minutes}:{secs:02d}'


def strip(source, target) -> None:
    """Copy every stream, drop every tag and chapter, write no new tags."""
    command = [
        'ffmpeg', '-v', 'error', '-y', '-i', str(source),
        '-map', '0',                       # keep every stream
        '-map_metadata', '-1',             # drop container and stream tags
        '-map_chapters', '-1',             # drop chapters
        '-c', 'copy',                      # no re-encode
        '-fflags', '+bitexact',            # do not write an "encoder" tag of our own
        '-flags:v', '+bitexact', '-flags:a', '+bitexact',
    ]
    if target.suffix.lower() in {'.mp4', '.m4v', '.mov'}:
        command += ['-movflags', '+faststart']
    command.append(str(target))

    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=FFMPEG_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        raise AppError('Processing the video took too long. Try a shorter clip.')

    if completed.returncode != 0 or not target.is_file():
        detail = (completed.stderr or '').strip().splitlines()
        reason = detail[-1] if detail else 'ffmpeg failed'
        raise AppError(f'Could not rewrite that video: {_short(reason)}')


@bp.post('/video-metadata-remover/run', endpoint='video_metadata_remover_run')
def run():
    _require_binaries()
    upload = get_file('file', allowed=VIDEO_EXTENSIONS | {'m4v', '3gp', 'mpg', 'mpeg', 'ts'})
    extension = extension_of(upload.filename)

    job_id = storage.new_job(TOOL)
    directory = storage.job_dir(TOOL, job_id)
    source = directory / f'source.{extension}'
    target = directory / f'clean.{extension}'
    upload.save(source)

    try:
        before = inspect(probe(source))
        strip(source, target)
        after = inspect(probe(target))
    finally:
        source.unlink(missing_ok=True)      # keep only the clean copy

    return ok(
        job_id=job_id,
        filename=target.name,
        before=before,
        after=after,
        removed=max(before['count'] - after['count'], 0),
        had_location=bool(before['location']),
        location=before['location'],
        size_after=target.stat().st_size,
        message=f'Removed {before["count"] - after["count"]} tag(s).',
    )
