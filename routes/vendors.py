from flask import Blueprint, request, jsonify
from models.models import db, Vendor
from flask_jwt_extended import jwt_required

from auth_utils import current_user_role

vendors_bp = Blueprint('vendors', __name__)


def require_admin():
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    return None


@vendors_bp.get('/vendors')
def get_vendors():
    return jsonify([v.to_dict() for v in Vendor.query.all()])


@vendors_bp.post('/vendors')
@jwt_required()
def create_vendor():
    err = require_admin()
    if err:
        return err
    data = request.get_json()
    v = Vendor(name=data['name'], contact=data.get('contact'), email=data.get('email'), address=data.get('address'))
    db.session.add(v)
    db.session.commit()
    return jsonify(v.to_dict()), 201


@vendors_bp.put('/vendors/<int:vid>')
@jwt_required()
def update_vendor(vid):
    err = require_admin()
    if err:
        return err
    v = Vendor.query.get_or_404(vid)
    data = request.get_json()
    for field in ('name', 'contact', 'email', 'address'):
        if field in data:
            setattr(v, field, data[field])
    db.session.commit()
    return jsonify(v.to_dict())


@vendors_bp.delete('/vendors/<int:vid>')
@jwt_required()
def delete_vendor(vid):
    err = require_admin()
    if err:
        return err
    v = Vendor.query.get_or_404(vid)
    db.session.delete(v)
    db.session.commit()
    return jsonify({'message': 'Deleted'})
