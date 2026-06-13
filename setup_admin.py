#!/usr/bin/env python3
"""
Quick admin setup script - creates a fresh admin account at admin@hok.com
Usage: python setup_admin.py
"""
import os
import sys
import bcrypt
from app import app, db
from models.models import User

def setup_admin():
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', app.config.get('SQLALCHEMY_DATABASE_URI'))
    
    with app.app_context():
        admin_email = "admin@hok.com"
        admin_password = "Admin@hok2026"
        admin_name = "Admin"
        
        try:
            # Delete all existing admins
            User.query.filter_by(role='admin').delete()
            db.session.commit()
            print("✓ Cleared old admin accounts")
            
            # Create fresh admin
            hashed = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt(rounds=11)).decode()
            admin = User(
                name=admin_name,
                email=admin_email,
                password_hash=hashed,
                role='admin',
                email_verified=True,
            )
            db.session.add(admin)
            db.session.commit()
            
            print("\n✓ ADMIN ACCOUNT CREATED")
            print(f"\n  📧 Email: {admin_email}")
            print(f"  🔑 Password: {admin_password}")
            print(f"  ✓ Ready for dashboard login")
            return 0
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return 1

if __name__ == '__main__':
    sys.exit(setup_admin())
