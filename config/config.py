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


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///interior.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'dev-secret-change-me')
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')

    # SendGrid / Email
    SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
    FROM_EMAIL = os.getenv('FROM_EMAIL', 'noreply@hokinteriors.com')
    EMAIL_FROM_NAME = os.getenv('EMAIL_FROM_NAME', 'HOK Interior Designs')

    # Connection pool (applies to PostgreSQL; SQLite ignores pool settings gracefully)
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'max_overflow': 20,
        'pool_timeout': 30,
        'pool_pre_ping': True,
    }

    JSONIFY_PRETTYPRINT_REGULAR = False
