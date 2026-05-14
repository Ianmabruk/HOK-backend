import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.engine import make_url

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


def _is_truthy(value: str | None) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _first_env(*names: str, default: str = '') -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _parse_size_bytes(value: str | None, default: int) -> int:
    text = str(value or '').strip().lower()
    if not text:
        return default
    multipliers = {
        'kb': 1024,
        'k': 1024,
        'mb': 1024 * 1024,
        'm': 1024 * 1024,
        'gb': 1024 * 1024 * 1024,
        'g': 1024 * 1024 * 1024,
    }
    for suffix, multiplier in multipliers.items():
        if text.endswith(suffix):
            return int(float(text[:-len(suffix)].strip()) * multiplier)
    try:
        return int(text)
    except ValueError:
        return default


def _is_production() -> bool:
    env = (os.getenv('APP_ENV') or os.getenv('FLASK_ENV') or '').strip().lower()
    if env:
        return env == 'production'
    return any(os.getenv(flag) for flag in ('RENDER', 'RAILWAY_ENVIRONMENT', 'HEROKU_APP_NAME'))


def _database_uri() -> str:
    database_url = os.getenv('DATABASE_URL', '').strip()
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)

        try:
            parsed_url = make_url(database_url)
        except Exception:
            return database_url

        if parsed_url.host and parsed_url.host.startswith('db.') and parsed_url.host.endswith('.supabase.co'):
            # Use Supabase transaction pooler by default to avoid platform-level direct-host issues.
            pooler_host = os.getenv('SUPABASE_POOLER_HOST', '').strip() or 'aws-0-eu-west-1.pooler.supabase.com'
            project_ref = parsed_url.host.split('.')[1]

            username = parsed_url.username
            if username in {None, '', 'postgres'} and project_ref:
                username = f'postgres.{project_ref}'

            parsed_url = parsed_url.set(
                host=pooler_host,
                port=6543,
                username=username,
            )
            return str(parsed_url)

        return database_url

    if os.getenv('RENDER'):
        raise RuntimeError(
            'DATABASE_URL is required in production. Render disks are ephemeral for the current SQLite fallback, '
            'so admin accounts, orders, chats, and products will be lost after restarts.'
        )

    return _default_sqlite_path()


def _validate_production_runtime(database_uri: str) -> None:
    if not _is_production():
        return

    if not database_uri:
        raise RuntimeError('Database configuration is missing in production.')

    allow_sqlite = _is_truthy(os.getenv('ALLOW_SQLITE_IN_PRODUCTION'))
    if database_uri.startswith('sqlite:') and not allow_sqlite:
        raise RuntimeError(
            'Refusing to run with SQLite in production because it can lose data on ephemeral hosts. '
            'Set DATABASE_URL to PostgreSQL/MySQL, or explicitly set ALLOW_SQLITE_IN_PRODUCTION=1 '
            'only if you have mounted persistent disk storage.'
        )

    jwt_secret = _first_env('JWT_SECRET_KEY', 'JWT_SECRET', 'SECRET_KEY')
    if not jwt_secret or jwt_secret in {
        'dev-secret-change-me',
        'change-this-super-secret-key-in-production',
        'generate-random-32-character-string',
        'generate-strong-random-string-in-production',
    }:
        raise RuntimeError('JWT_SECRET_KEY or JWT_SECRET must be set to a strong value in production.')


_RESOLVED_DATABASE_URI = _database_uri()
_validate_production_runtime(_RESOLVED_DATABASE_URI)
_IS_SQLITE_DATABASE = _RESOLVED_DATABASE_URI.startswith('sqlite:')


class Config:
    SQLALCHEMY_DATABASE_URI = _RESOLVED_DATABASE_URI
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = _first_env('JWT_SECRET_KEY', 'JWT_SECRET', 'SECRET_KEY', default='dev-secret-change-me')
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')
    BACKEND_PUBLIC_URL = os.getenv('BACKEND_PUBLIC_URL', '').strip()
    SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip()
    SUPABASE_SERVICE_ROLE_KEY = _first_env('SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_KEY')
    SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY', '').strip()
    SUPABASE_MEDIA_BUCKET = os.getenv('SUPABASE_MEDIA_BUCKET', 'media').strip() or 'media'
    UPLOAD_FOLDER = os.getenv(
        'UPLOAD_FOLDER',
        '/tmp/hok-uploads' if _is_production() else str(Path(__file__).resolve().parent.parent / 'uploads'),
    )
    MAX_CONTENT_LENGTH = _parse_size_bytes(os.getenv('MAX_UPLOAD_SIZE'), 120 * 1024 * 1024)
    APP_ENV = (os.getenv('APP_ENV') or os.getenv('FLASK_ENV') or 'development').strip().lower()

    ADMIN_NAME = os.getenv('ADMIN_NAME', 'Admin').strip() or 'Admin'
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@hokinterior.com').strip().lower()
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'Admin@1234')
    BCRYPT_LOG_ROUNDS = int(os.getenv('BCRYPT_LOG_ROUNDS', '9'))

    # Optional Cloudinary media storage
    CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET')

    # SendGrid / Email
    SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
    FROM_EMAIL = os.getenv('FROM_EMAIL', '').strip()
    EMAIL_FROM_NAME = os.getenv('EMAIL_FROM_NAME', 'HOK Interior Designs')

    # Connection pool (applies to PostgreSQL; SQLite ignores pool settings gracefully)
    SQLALCHEMY_ENGINE_OPTIONS = (
        {'connect_args': {'timeout': 30}}
        if _IS_SQLITE_DATABASE
        else {
            'pool_size': int(os.getenv('DB_POOL_SIZE', '10')),
            'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', '20')),
            'pool_timeout': int(os.getenv('DB_POOL_TIMEOUT', '30')),
            'pool_pre_ping': True,
            'pool_recycle': int(os.getenv('DB_POOL_RECYCLE', '1800')),
        }
    )

    JSONIFY_PRETTYPRINT_REGULAR = False
