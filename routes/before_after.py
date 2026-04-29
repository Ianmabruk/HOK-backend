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

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from auth_utils import current_user_role
from models.models import BeforeAfterProject, db

before_after_bp = Blueprint("before_after", __name__)
logger = logging.getLogger(__name__)


@before_after_bp.get("/before-after")
def list_projects():
    projects = BeforeAfterProject.query.order_by(
        BeforeAfterProject.sort_order, BeforeAfterProject.created_at
    ).all()
    return jsonify([p.to_dict() for p in projects]), 200


@before_after_bp.post("/before-after")
@jwt_required()

def create_project():
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    data = request.get_json(silent=True) or {}
    if not data.get("title", "").strip():
        return jsonify({"message": "Title is required"}), 400

    project = BeforeAfterProject(
        title=data["title"].strip(),
        description=data.get("description", "").strip() or None,
        room_type=data.get("room_type", "").strip() or None,
        style=data.get("style", "").strip() or None,
        before_video_url=data.get("before_video_url", "").strip() or None,
        after_video_url=data.get("after_video_url", "").strip() or None,
        before_poster_url=data.get("before_poster_url", "").strip() or None,
        after_poster_url=data.get("after_poster_url", "").strip() or None,
        sort_order=int(data.get("sort_order", 0)),
    )
    db.session.add(project)
    db.session.commit()
    return jsonify(project.to_dict()), 201


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
    if "description" in data:
        project.description = data["description"].strip() or None
    if "room_type" in data:
        project.room_type = data["room_type"].strip() or None
    if "style" in data:
        project.style = data["style"].strip() or None
    if "before_video_url" in data:
        project.before_video_url = data["before_video_url"].strip() or None
    if "after_video_url" in data:
        project.after_video_url = data["after_video_url"].strip() or None
    if "before_poster_url" in data:
        project.before_poster_url = data["before_poster_url"].strip() or None
    if "after_poster_url" in data:
        project.after_poster_url = data["after_poster_url"].strip() or None
    if "sort_order" in data:
        project.sort_order = int(data["sort_order"])

    db.session.commit()
    return jsonify(project.to_dict()), 200


@before_after_bp.delete("/before-after/<int:project_id>")
@jwt_required()

def delete_project(project_id):
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    project = db.session.get(BeforeAfterProject, project_id)
    if not project:
        return jsonify({"message": "Project not found"}), 404
    db.session.delete(project)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200
