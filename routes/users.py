from flask import Blueprint, jsonify
from models.models import User
from flask_jwt_extended import jwt_required, get_jwt_identity

users_bp = Blueprint('users', __name__)


@users_bp.get('/users')
@jwt_required()
def get_users():
    identity = get_jwt_identity()
    if identity.get('role') != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([u.to_dict() for u in users])
