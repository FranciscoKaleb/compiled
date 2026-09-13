"""Per-job scratch storage for the tools.

Replaces the counter.txt read-modify-write that was copy-pasted into all three
tools. That scheme had two problems this fixes: concurrent uploads could claim
the same id and overwrite each other, and any visitor could walk
/tools/tool1/download/1..N and read other people's files.

Job ids are unguessable and recorded in the session, so a download only works
for the browser that created it.
"""
import secrets
import shutil
import time
from pathlib import Path

from flask import current_app, session

from app.core.errors import AppError

SESSION_KEY = 'tool_jobs'
_MAX_TRACKED = 50


def _root(tool: str) -> Path:
    return Path(current_app.config['TOOLS_DIR']) / tool


def new_job(tool: str) -> str:
    """Create a job directory and remember it for this browser session."""
    purge_old(tool)
    job_id = secrets.token_urlsafe(12)
    (_root(tool) / job_id).mkdir(parents=True, exist_ok=True)

    owned = session.get(SESSION_KEY, {})
    jobs = owned.setdefault(tool, [])
    jobs.append(job_id)
    del jobs[:-_MAX_TRACKED]          # keep the session cookie small
    session[SESSION_KEY] = owned
    session.modified = True
    return job_id


def job_dir(tool: str, job_id: str) -> Path:
    """The directory for a job this session owns, or an error."""
    owned = session.get(SESSION_KEY, {}).get(tool, [])
    if job_id not in owned:
        raise AppError('That file is not available — run the tool again.', 404)

    path = _root(tool) / job_id
    if not path.is_dir():
        raise AppError('That result has expired — run the tool again.', 404)
    return path


def job_file(tool: str, job_id: str, name: str) -> Path:
    path = job_dir(tool, job_id) / name
    if not path.is_file():
        raise AppError('That result has expired — run the tool again.', 404)
    return path


def purge_old(tool: str) -> int:
    """Delete job directories past their TTL. Returns how many were removed."""
    root = _root(tool)
    if not root.is_dir():
        return 0

    cutoff = time.time() - current_app.config['TOOL_JOB_TTL_HOURS'] * 3600
    removed = 0
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        try:
            if entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed
