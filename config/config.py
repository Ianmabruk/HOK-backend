import os
from pathlib import Path
from dotenv import load_dotenv

# 1. Load backend-specific vars (highest priority)
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

# 2. Also pick up root project .env for shared keys (e.g. SENDGRID_API_KEY, FROM_EMAIL)
#    override=False means backend/.env values win when the same key appears in both files
_root_env = Path(__file__).resolve().parent.parent.parent / '.env'
if _root_env.exists():
    load_dotenv(dotenv_path=_root_env, override=False)


def _default_sqlite_path() -> str:
    db_path = Path(__file__).resolve().parent.parent / 'instance' / 'interior.db'
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f'sqlite:///{db_path}'


def _database_uri() -> str:
    database_url = os.getenv('DATABASE_URL', '').strip()
    if database_url:
        if database_url.startswith('postgres://'):
            return database_url.replace('postgres://', 'postgresql://', 1)
        return database_url

    if os.getenv('RENDER'):
        raise RuntimeError(
            'DATABASE_URL is required in production. Render disks are ephemeral for the current SQLite fallback, '
            'so admin accounts, orders, chats, and products will be lost after restarts.'
        )

    return _default_sqlite_path()


class Config:
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'dev-secret-change-me')
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')
    BACKEND_PUBLIC_URL = os.getenv('BACKEND_PUBLIC_URL', '').strip()
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', str(Path(__file__).resolve().parent.parent / 'uploads'))

    ADMIN_NAME = os.getenv('ADMIN_NAME', 'Admin').strip() or 'Admin'
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@hokinterior.com').strip().lower()
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'Admin@1234')

    # Optional Cloudinary media storage
    CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET')

    # SendGrid / Email
    SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
    FROM_EMAIL = os.getenv('FROM_EMAIL', '').strip()
    EMAIL_FROM_NAME = os.getenv('EMAIL_FROM_NAME', 'HOK Interior Designs')

    # Connection pool (applies to PostgreSQL; SQLite ignores pool settings gracefully)
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'max_overflow': 20,
        'pool_timeout': 30,
        'pool_pre_ping': True,
    }

    JSONIFY_PRETTYPRINT_REGULAR = False
