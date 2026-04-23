import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///interior.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'dev-secret-change-me')
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')

    # Connection pool (applies to PostgreSQL; SQLite ignores pool settings gracefully)
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'max_overflow': 20,
        'pool_timeout': 30,
        'pool_pre_ping': True,  # detect stale connections
    }

    # Compress JSON responses
    JSONIFY_PRETTYPRINT_REGULAR = False
