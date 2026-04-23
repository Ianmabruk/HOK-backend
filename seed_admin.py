"""
Run this once to create an admin account:
  python seed_admin.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from models.models import db, User
import bcrypt

ADMIN_NAME = os.getenv('ADMIN_NAME', 'Admin')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@hokinterior.com')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'Admin@1234')

with app.app_context():
    existing = User.query.filter_by(email=ADMIN_EMAIL).first()
    if existing:
        print(f'Admin already exists: {ADMIN_EMAIL}')
    else:
        hashed = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
        admin = User(name=ADMIN_NAME, email=ADMIN_EMAIL, password=hashed, role='admin')
        db.session.add(admin)
        db.session.commit()
        print(f'Admin created: {ADMIN_EMAIL} / {ADMIN_PASSWORD}')
        print('IMPORTANT: Change the password after first login!')
