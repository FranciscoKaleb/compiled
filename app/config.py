"""Application configuration, driven by the environment.

Every path the app writes to hangs off DATA_DIR, and every secret comes from
the environment. Nothing here should ever contain a real credential.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Repo root: .../compiled/compiled — the parent of the `app` package.
ROOT_DIR = Path(__file__).resolve().parent.parent

load_dotenv(ROOT_DIR / '.env')


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


class Config:
    # --- paths -------------------------------------------------------------
    # All large/generated data lives outside the source tree and is gitignored.
    DATA_DIR = Path(os.environ.get('DATA_DIR', ROOT_DIR / 'app_files'))
    MODELS_DIR = DATA_DIR / 'models'
    TOOLS_DIR = DATA_DIR / 'tools_files'
    DB_DIR = DATA_DIR / 'db'

    # --- database ----------------------------------------------------------
    # SQLite by default so a fresh clone works with no server to install.
    # Point DATABASE_URL at MySQL to switch: mysql+pymysql://user:pw@host/db
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', f'sqlite:///{DB_DIR / "app.db"}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- flask -------------------------------------------------------------
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-only-not-for-production')
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_UPLOAD_MB', 500)) * 1024 * 1024
    DEBUG = _bool('FLASK_DEBUG', False)

    # --- inference ---------------------------------------------------------
    # Cosine-similarity cut-offs, kept here so they are tunable in one place.
    FACE_MATCH_THRESHOLD = float(os.environ.get('FACE_MATCH_THRESHOLD', 0.65))
    FACE_COMPARE_THRESHOLD = float(os.environ.get('FACE_COMPARE_THRESHOLD', 0.4))

    # How long a tool's output files are kept before being purged.
    TOOL_JOB_TTL_HOURS = int(os.environ.get('TOOL_JOB_TTL_HOURS', 24))

    @classmethod
    def ensure_dirs(cls):
        for path in (cls.DATA_DIR, cls.MODELS_DIR, cls.TOOLS_DIR, cls.DB_DIR):
            path.mkdir(parents=True, exist_ok=True)
