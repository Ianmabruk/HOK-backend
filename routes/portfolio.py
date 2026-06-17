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
from sqlalchemy import String, cast

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


def _find_project_by_id(pid: str):
    project_id = str(pid or '').strip()
    if not project_id:
        return None
    if project_id.isdigit():
        return db.session.get(PortfolioProject, int(project_id))
    return (
        PortfolioProject.query
        .filter(cast(PortfolioProject.id, String) == project_id)
        .first()
    )


def _clean_text(value, max_len=None):
    text = str(value or '').strip()
    if not text:
        return None
    return text[:max_len] if max_len else text


def _clean_json_list(value):
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = __import__('json').loads(text)
            return parsed if isinstance(parsed, list) else None
        except Exception:
            return None
    return None


@portfolio_bp.get('/portfolio')
def list_projects():
    try:
        projects = (
            PortfolioProject.query
            .filter(PortfolioProject.is_published == True)
            .order_by(
                PortfolioProject.sort_order.asc(),
                PortfolioProject.created_at.desc(),
            )
            .limit(20)
            .all()
        )
        return jsonify([p.to_dict() for p in projects]), 200
    except Exception:
        db.session.rollback()
        logger.exception('Failed to load published portfolio projects; returning empty list | %s', _request_error_context())
        return jsonify({'error': 'Failed to load portfolio', 'projects': []}), 500


@portfolio_bp.get('/portfolio/all')
@jwt_required()
def list_all_projects():
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    try:
        projects = PortfolioProject.query.order_by(
            PortfolioProject.created_at.desc(),
            PortfolioProject.sort_order.asc(),
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
        title=(data.get('title') or '').strip(),
        summary=_clean_text(data.get('summary'), 400),
        description=_clean_text(data.get('description'), 5000),
        image_url=_clean_text(data.get('image_url')),
        video_url=_clean_text(data.get('video_url')),
        room_type=_clean_text(data.get('room_type'), 80),
        style=_clean_text(data.get('style'), 80),
        category=_clean_text(data.get('category'), 80),
        status=_clean_text(data.get('status'), 30) or 'completed',
        completion_date=_clean_text(data.get('completion_date'), 30),
        testimonials=_clean_json_list(data.get('testimonials')),
        year=_clean_text(data.get('year'), 10),
        location=_clean_text(data.get('location'), 120),
        sort_order=int(data.get('sort_order') or 0),
        is_published=bool(data.get('is_published', True)),
        is_featured=bool(data.get('is_featured', False)),
        display_order=int(data.get('display_order') or 0),
        media_type=_clean_text(data.get('media_type'), 20) or ('video' if data.get('video_url') else 'image'),
        motion_effect=_clean_text(data.get('motion_effect'), 40) or 'none',
    )
    db.session.add(p)
    db.session.commit()
    return jsonify(p.to_dict()), 201


@portfolio_bp.put('/portfolio/<pid>')
@jwt_required()
def update_project(pid):
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    p = _find_project_by_id(pid)
    if not p:
        return jsonify({'message': 'Project not found'}), 404
    data = request.get_json(silent=True) or {}
    for field in ('title', 'summary', 'description', 'image_url', 'video_url', 'room_type', 'style', 'category', 'status', 'completion_date', 'year', 'location'):
        if field in data:
            setattr(p, field, _clean_text(data[field]) or (None if field != 'title' else p.title))
    if 'testimonials' in data:
        p.testimonials = _clean_json_list(data.get('testimonials'))
    if 'sort_order' in data:
        p.sort_order = int(data['sort_order'] or 0)
    if 'is_published' in data:
        p.is_published = bool(data.get('is_published'))
    if 'is_featured' in data:
        p.is_featured = bool(data.get('is_featured'))
    if 'display_order' in data:
        p.display_order = int(data.get('display_order') or 0)
    if 'media_type' in data:
        p.media_type = _clean_text(data.get('media_type'), 20) or ('video' if p.video_url else 'image')
    if 'motion_effect' in data:
        p.motion_effect = _clean_text(data.get('motion_effect'), 40) or 'none'
    db.session.commit()
    return jsonify(p.to_dict()), 200


@portfolio_bp.delete('/portfolio/<pid>')
@jwt_required()
def delete_project(pid):
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    p = _find_project_by_id(pid)
    if not p:
        return jsonify({'message': 'Project not found'}), 404
    db.session.delete(p)
    db.session.commit()
    return jsonify({'message': 'Deleted'}), 200
