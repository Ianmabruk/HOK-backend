from flask import Blueprint, request, jsonify
from models.models import db, Vendor
from flask_jwt_extended import jwt_required
import logging

from auth_utils import current_user_role

vendors_bp = Blueprint('vendors', __name__)
logger = logging.getLogger(__name__)


def _clean_text(value):
    return str(value or '').strip() or None


def require_admin():
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    return None


@vendors_bp.get('/vendors')
def get_vendors():
    try:
        return jsonify([v.to_dict() for v in Vendor.query.all()])
    except Exception:
        db.session.rollback()
        logger.exception('Failed to list vendors; returning empty list')
        return jsonify([]), 200


@vendors_bp.post('/vendors')
@jwt_required()
def create_vendor():
    err = require_admin()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    name = _clean_text(data.get('name'))
    if not name:
        return jsonify({'error': 'Invalid input', 'field': 'name', 'message': 'Vendor name is required'}), 400

    try:
        v = Vendor(
            name=name,
            contact=_clean_text(data.get('contact')),
            email=_clean_text(data.get('email')),
            address=_clean_text(data.get('address')),
        )
        db.session.add(v)
        db.session.commit()
        return jsonify(v.to_dict()), 201
    except Exception:
        db.session.rollback()
        logger.exception('Failed to create vendor')
        return jsonify({'error': 'Unexpected server error', 'message': 'Could not create vendor'}), 500


@vendors_bp.put('/vendors/<int:vid>')
@jwt_required()
def update_vendor(vid):
    err = require_admin()
    if err:
        return err
    v = Vendor.query.get_or_404(vid)
    data = request.get_json(silent=True) or {}
    if 'name' in data:
        name = _clean_text(data.get('name'))
        if not name:
            return jsonify({'error': 'Invalid input', 'field': 'name', 'message': 'Vendor name cannot be empty'}), 400
        v.name = name

    for field in ('contact', 'email', 'address'):
        if field in data:
            setattr(v, field, _clean_text(data.get(field)))

    try:
        db.session.commit()
        return jsonify(v.to_dict())
    except Exception:
        db.session.rollback()
        logger.exception('Failed to update vendor id=%s', vid)
        return jsonify({'error': 'Unexpected server error', 'message': 'Could not update vendor'}), 500


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
