"""
Portfolio project routes.

GET    /api/portfolio          - list published projects (public)
GET    /api/portfolio/all      - list all projects incl. drafts (admin)
POST   /api/portfolio          - create project (admin)
PUT    /api/portfolio/<id>     - update project (admin)
DELETE /api/portfolio/<id>     - delete project (admin)
"""
import logging
import uuid

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from auth_utils import current_user_role
from models.models import PortfolioProject, db

portfolio_bp = Blueprint('portfolio', __name__)
logger = logging.getLogger(__name__)


def _request_error_context() -> str:
    request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
    return (
        f"request_id={request_id} method={request.method} path={request.path} "
        f"remote_addr={request.remote_addr}"
    )


@portfolio_bp.get('/portfolio')
def list_projects():
    try:
        projects = PortfolioProject.query.filter(
            PortfolioProject.is_published.isnot(False)
        ).order_by(PortfolioProject.sort_order, PortfolioProject.created_at).all()
        return jsonify([p.to_dict() for p in projects]), 200
    except Exception:
        db.session.rollback()
        logger.exception('Failed to load published portfolio projects; returning empty list | %s', _request_error_context())
        return jsonify([]), 200


@portfolio_bp.get('/portfolio/all')
@jwt_required()
def list_all_projects():
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    try:
        projects = PortfolioProject.query.order_by(
            PortfolioProject.sort_order, PortfolioProject.created_at
        ).all()
        return jsonify([p.to_dict() for p in projects]), 200
    except Exception:
        db.session.rollback()
        logger.exception('Failed to load all portfolio projects; returning empty list | %s', _request_error_context())
        return jsonify([]), 200


@portfolio_bp.post('/portfolio')
@jwt_required()
def create_project():
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    data = request.get_json(silent=True) or {}
    if not (data.get('title') or '').strip():
        return jsonify({'message': 'Title is required'}), 400
    p = PortfolioProject(
        title=data['title'].strip(),
        summary=(data.get('summary') or '').strip() or None,
        description=(data.get('description') or '').strip() or None,
        image_url=(data.get('image_url') or '').strip() or None,
        video_url=(data.get('video_url') or '').strip() or None,
        room_type=(data.get('room_type') or '').strip() or None,
        style=(data.get('style') or '').strip() or None,
        year=(data.get('year') or '').strip() or None,
        location=(data.get('location') or '').strip() or None,
        sort_order=int(data.get('sort_order') or 0),
        is_published=bool(data.get('is_published', True)),
    )
    db.session.add(p)
    db.session.commit()
    return jsonify(p.to_dict()), 201


@portfolio_bp.put('/portfolio/<int:pid>')
@jwt_required()
def update_project(pid):
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    p = db.session.get(PortfolioProject, pid)
    if not p:
        return jsonify({'message': 'Project not found'}), 404
    data = request.get_json(silent=True) or {}
    for field in ('title', 'summary', 'description', 'image_url', 'video_url', 'room_type', 'style', 'year', 'location'):
        if field in data:
            p.__setattr__(field, (data[field] or '').strip() or None)
    if 'sort_order' in data:
        p.sort_order = int(data['sort_order'] or 0)
    if 'is_published' in data:
        p.is_published = bool(data['is_published'])
    db.session.commit()
    return jsonify(p.to_dict()), 200


@portfolio_bp.delete('/portfolio/<int:pid>')
@jwt_required()
def delete_project(pid):
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    p = db.session.get(PortfolioProject, pid)
    if not p:
        return jsonify({'message': 'Project not found'}), 404
    db.session.delete(p)
    db.session.commit()
    return jsonify({'message': 'Deleted'}), 200
