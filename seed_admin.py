"""
Run this once to create an admin account:
  python seed_admin.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import bcrypt
from sqlalchemy import func
from app import app
from models.models import db, User

with app.app_context():
  ADMIN_NAME = app.config.get('ADMIN_NAME', 'Admin')
  ADMIN_EMAIL = (app.config.get('ADMIN_EMAIL', 'admin@hokinterior.com') or '').strip().lower()
  ADMIN_PASSWORD = app.config.get('ADMIN_PASSWORD', 'Admin@1234')

  existing_admin = User.query.filter(
    (func.lower(User.role) == 'admin') | (func.lower(User.email) == ADMIN_EMAIL)
  ).order_by(User.id.asc()).first()
  hashed = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()

  if existing_admin:
    existing_admin.name = ADMIN_NAME
    existing_admin.email = ADMIN_EMAIL
    existing_admin.password = hashed
    existing_admin.role = 'admin'
    existing_admin.email_verified = True
    db.session.commit()
    print(f'Admin credentials updated: {ADMIN_EMAIL} / {ADMIN_PASSWORD}')
  else:
    admin = User(
      name=ADMIN_NAME,
      email=ADMIN_EMAIL,
      password=hashed,
      role='admin',
      email_verified=True,
    )
    db.session.add(admin)
    db.session.commit()
    print(f'Admin created: {ADMIN_EMAIL} / {ADMIN_PASSWORD}')
    print('IMPORTANT: Change the password after first login!')
