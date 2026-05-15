"""
Before & After project routes.

Endpoints
─────────
GET    /api/before-after          – list all projects (public)
POST   /api/before-after          – create project (admin only)
PUT    /api/before-after/<id>     – update project (admin only)
DELETE /api/before-after/<id>     – delete project (admin only)
"""

import logging
import uuid

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import inspect

from auth_utils import current_user_role
from models.models import BeforeAfterProject, db

before_after_bp = Blueprint("before_after", __name__)
logger = logging.getLogger(__name__)


def _request_error_context() -> str:
    request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
    return (
        f"request_id={request_id} method={request.method} path={request.path} "
        f"remote_addr={request.remote_addr}"
    )


def _safe_int(value, default=0):
    try:
        if value is None or value == '':
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _before_after_order_exprs():
    try:
        columns = {c['name'] for c in inspect(db.engine).get_columns('before_after_projects')}
    except Exception:
        db.session.rollback()
        return [BeforeAfterProject.created_at.desc()]

    if 'sort_order' in columns:
        return [BeforeAfterProject.sort_order, BeforeAfterProject.created_at]
    return [BeforeAfterProject.created_at.desc()]


@before_after_bp.get("/before-after")
def list_projects():
    # Use isnot(False) so existing NULL rows (before migration) are also included
    try:
        projects = BeforeAfterProject.query.filter(
            BeforeAfterProject.is_published.isnot(False)
        ).order_by(*_before_after_order_exprs()).all()
        return jsonify([p.to_dict() for p in projects]), 200
    except Exception:
        db.session.rollback()
        logger.exception('Failed to list published before-after projects; returning empty list | %s', _request_error_context())
        return jsonify([]), 200


@before_after_bp.get("/before-after/all")
@jwt_required()
def list_all_projects():
    """Admin-only: returns all projects including unpublished."""
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    try:
        projects = BeforeAfterProject.query.order_by(*_before_after_order_exprs()).all()
        return jsonify([p.to_dict() for p in projects]), 200
    except Exception:
        db.session.rollback()
        logger.exception('Failed to list all before-after projects; returning empty list | %s', _request_error_context())
        return jsonify([]), 200


@before_after_bp.post("/before-after")
@jwt_required()

def create_project():
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    data = request.get_json(silent=True) or {}
    if not data.get("title", "").strip():
        return jsonify({"message": "Title is required"}), 400

    try:
        project = BeforeAfterProject(
            title=data["title"].strip(),
            description=(data.get("description") or "").strip() or None,
            room_type=(data.get("room_type") or "").strip() or None,
            style=(data.get("style") or "").strip() or None,
            before_video_url=(data.get("before_video_url") or "").strip() or None,
            after_video_url=(data.get("after_video_url") or "").strip() or None,
            before_poster_url=(data.get("before_poster_url") or "").strip() or None,
            after_poster_url=(data.get("after_poster_url") or "").strip() or None,
            sort_order=_safe_int(data.get("sort_order"), 0),
            is_published=bool(data.get("is_published", True)),
        )
        db.session.add(project)
        db.session.commit()
        return jsonify(project.to_dict()), 201
    except Exception:
        db.session.rollback()
        logger.exception('Failed to create before-after project | %s', _request_error_context())
        return jsonify({'message': 'Could not create project. Check required fields and media URLs.'}), 400


@before_after_bp.put("/before-after/<int:project_id>")
@jwt_required()

def update_project(project_id):
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    project = db.session.get(BeforeAfterProject, project_id)
    if not project:
        return jsonify({"message": "Project not found"}), 404

    data = request.get_json(silent=True) or {}
    if "title" in data:
        title = data["title"].strip()
        if not title:
            return jsonify({"message": "Title is required"}), 400
        project.title = title
    try:
        if "description" in data:
            project.description = (data["description"] or '').strip() or None
        if "room_type" in data:
            project.room_type = (data["room_type"] or '').strip() or None
        if "style" in data:
            project.style = (data["style"] or '').strip() or None
        if "before_video_url" in data:
            project.before_video_url = (data["before_video_url"] or '').strip() or None
        if "after_video_url" in data:
            project.after_video_url = (data["after_video_url"] or '').strip() or None
        if "before_poster_url" in data:
            project.before_poster_url = (data["before_poster_url"] or '').strip() or None
        if "after_poster_url" in data:
            project.after_poster_url = (data["after_poster_url"] or '').strip() or None
        if "sort_order" in data:
            project.sort_order = _safe_int(data["sort_order"], project.sort_order or 0)
        if "is_published" in data:
            project.is_published = bool(data["is_published"])

        db.session.commit()
        return jsonify(project.to_dict()), 200
    except Exception:
        db.session.rollback()
        logger.exception('Failed to update before-after project id=%s | %s', project_id, _request_error_context())
        return jsonify({'message': 'Could not update project. Check payload values.'}), 400


@before_after_bp.delete("/before-after/<int:project_id>")
@jwt_required()

def delete_project(project_id):
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    project = db.session.get(BeforeAfterProject, project_id)
    if not project:
        return jsonify({"message": "Project not found"}), 404
    try:
        db.session.delete(project)
        db.session.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        db.session.rollback()
        logger.exception('Failed to delete before-after project id=%s | %s', project_id, _request_error_context())
        return jsonify({'message': 'Could not delete project.'}), 400
