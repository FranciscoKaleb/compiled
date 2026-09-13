"""Helpers shared by the tool handlers.

Everything a tool does is: take uploads, write results into its job directory,
return `result(...)`. These helpers cover the parts that would otherwise be
copy-pasted forty times.
"""
import re
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

from flask import request
from werkzeug.utils import secure_filename

from app.core import storage
from app.core.errors import AppError
from app.core.responses import ok
from app.core.uploads import extension_of


# ---------------------------------------------------------------------------
# Jobs and files
# ---------------------------------------------------------------------------

class Job:
    """A tool run: an id, a directory, and the files written into it."""

    def __init__(self, tool: str):
        self.tool = tool
        self.id = storage.new_job(tool)
        self.dir: Path = storage.job_dir(tool, self.id)

    def path(self, name: str) -> Path:
        return self.dir / name

    def save_upload(self, upload, name: str | None = None) -> Path:
        """Save an upload under a safe name and return its path."""
        name = name or safe_name(upload.filename)
        path = self.dir / name
        upload.save(path)
        return path

    def zip(self, files: list[Path], name: str = 'result.zip', arcnames=None) -> Path:
        target = self.dir / name
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
            for index, file in enumerate(files):
                arc = arcnames[index] if arcnames else file.name
                archive.write(file, arc)
        return target

    def cleanup(self, *paths: Path) -> None:
        for path in paths:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)


def safe_name(filename: str | None, fallback: str = 'file') -> str:
    name = secure_filename(filename or '') or fallback
    return name[:120]


def stem_of(filename: str | None) -> str:
    return Path(safe_name(filename)).stem or 'file'


def uploads(field: str = 'files', *, allowed: set[str] | None = None, minimum: int = 1):
    files = [f for f in request.files.getlist(field) if f and f.filename]
    if len(files) < minimum:
        noun = 'file' if minimum == 1 else 'files'
        raise AppError(f'Choose at least {minimum} {noun}.')
    if allowed is not None:
        for f in files:
            if extension_of(f.filename) not in allowed:
                raise AppError(f'"{f.filename}" is not a supported file type.')
    return files


def result(job: Job, *, filename: str | None = None, message: str = 'Done.',
           facts: list | None = None, text: str | None = None,
           extra_files: list[str] | None = None, **more):
    """The one response shape tools.js understands."""
    payload = {
        'job_id': job.id,
        'filename': filename,
        'message': message,
        'facts': facts or [],
        'extra_files': extra_files or [],
    }
    if filename:
        payload['size'] = job.path(filename).stat().st_size
    if text is not None:
        payload['text'] = text
    payload.update(more)
    return ok(**payload)


# ---------------------------------------------------------------------------
# Form parsing
# ---------------------------------------------------------------------------

def form_int(name: str, default: int, lo: int | None = None, hi: int | None = None) -> int:
    try:
        value = int(float(request.form.get(name, default)))
    except (TypeError, ValueError):
        value = default
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


def form_float(name: str, default: float, lo: float | None = None, hi: float | None = None) -> float:
    try:
        value = float(request.form.get(name, default))
    except (TypeError, ValueError):
        value = default
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


def form_str(name: str, default: str = '') -> str:
    return (request.form.get(name) or default).strip()


def form_bool(name: str) -> bool:
    return request.form.get(name, '').lower() in {'1', 'true', 'on', 'yes'}


def form_choice(name: str, options: list[str], default: str) -> str:
    value = form_str(name, default)
    return value if value in options else default


def parse_pages(text: str, total: int) -> list[int]:
    """'1-3, 5, 8-' -> zero-based page indexes, validated against `total`."""
    pages: list[int] = []
    for part in re.split(r'[,\s]+', text.strip()):
        if not part:
            continue
        match = re.fullmatch(r'(\d+)?-(\d+)?', part)
        if match and '-' in part:
            start = int(match.group(1) or 1)
            end = int(match.group(2) or total)
        elif part.isdigit():
            start = end = int(part)
        else:
            raise AppError(f'"{part}" is not a page number or range.')
        if start < 1 or end > total or start > end:
            raise AppError(f'"{part}" is outside this document\'s {total} page(s).')
        pages.extend(range(start - 1, end))
    return pages


def parse_timestamp(text: str, default: float | None = None) -> float | None:
    """'90', '1:30', '0:01:30', '1:30.5' -> seconds."""
    text = (text or '').strip()
    if not text:
        return default
    parts = text.split(':')
    if len(parts) > 3 or not all(re.fullmatch(r'\d+(\.\d+)?', p) for p in parts):
        raise AppError(f'"{text}" is not a time. Use seconds, mm:ss or h:mm:ss.')
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


def human_time(seconds: float) -> str:
    seconds = int(round(seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours}:{minutes:02d}:{secs:02d}' if hours else f'{minutes}:{secs:02d}'


def human_bytes(size: int | float) -> str:
    size = float(size)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.1f} GB'


# ---------------------------------------------------------------------------
# External programs
# ---------------------------------------------------------------------------

def require(*binaries: str) -> None:
    missing = [b for b in binaries if not shutil.which(b)]
    if missing:
        raise AppError(f'{", ".join(missing)} is not installed on the machine running this app.', 503)


def run(command: list, *, timeout: int = 600, what: str = 'The command') -> subprocess.CompletedProcess:
    """Run a subprocess, turning failure into a readable AppError."""
    try:
        completed = subprocess.run(
            [str(c) for c in command], capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        raise AppError(f'{what} took too long and was stopped. Try a smaller file.')
    except FileNotFoundError:
        raise AppError(f'{command[0]} is not installed on the machine running this app.', 503)

    if completed.returncode != 0:
        lines = [l for l in (completed.stderr or '').strip().splitlines() if l.strip()]
        detail = lines[-1][:200] if lines else f'exit code {completed.returncode}'
        raise AppError(f'{what} failed: {detail}')
    return completed


def ffmpeg(*args, timeout: int = 900) -> subprocess.CompletedProcess:
    require('ffmpeg')
    return run(['ffmpeg', '-v', 'error', '-y', *args], timeout=timeout, what='ffmpeg')


def ffprobe_json(path) -> dict:
    import json

    require('ffprobe')
    completed = run(
        ['ffprobe', '-v', 'error', '-print_format', 'json',
         '-show_format', '-show_streams', str(path)],
        timeout=60, what='Reading the media file',
    )
    return json.loads(completed.stdout or '{}')


def media_duration(path) -> float:
    info = ffprobe_json(path)
    try:
        return float(info['format']['duration'])
    except (KeyError, TypeError, ValueError):
        return 0.0


def today() -> str:
    return datetime.now().strftime('%Y-%m-%d')
