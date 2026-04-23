from flask import Blueprint, request, jsonify
from models.models import db, User
import bcrypt
from flask_jwt_extended import create_access_token

auth_bp = Blueprint('auth', __name__)


@auth_bp.post('/register')
def register():
    data = request.get_json()
    if not data or not all(k in data for k in ('name', 'email', 'password')):
        return jsonify({'message': 'Missing fields'}), 400

    if User.query.filter_by(email=data['email'].lower().strip()).first():
        return jsonify({'message': 'Email already registered'}), 409

    # First user ever registered automatically becomes admin
    is_first_user = User.query.count() == 0
    hashed = bcrypt.hashpw(data['password'].encode(), bcrypt.gensalt()).decode()
    role = 'admin' if is_first_user else 'customer'
    user = User(name=data['name'].strip(), email=data['email'].lower().strip(),
                password=hashed, role=role)
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity={'id': user.id, 'role': user.role})
    return jsonify({'user': user.to_dict(), 'token': token}), 201


@auth_bp.post('/login')
def login():
    data = request.get_json()
    if not data or not all(k in data for k in ('email', 'password')):
        return jsonify({'message': 'Missing fields'}), 400

    user = User.query.filter_by(email=data['email'].lower().strip()).first()
    if not user or not bcrypt.checkpw(data['password'].encode(), user.password.encode()):
        return jsonify({'message': 'Invalid credentials'}), 401

    token = create_access_token(identity={'id': user.id, 'role': user.role})
    return jsonify({'user': user.to_dict(), 'token': token}), 200
