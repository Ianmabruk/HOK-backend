"""
Projects route - combines portfolio and before-after projects.
GET /api/projects - list published projects from both sources
"""
from hashlib import sha1

from flask import Blueprint, jsonify
from models.models import BeforeAfterProject, PortfolioProject

projects_bp = Blueprint('projects', __name__)


def _media_token(value):
    value = str(value or '').strip()
    if not value:
        return ''
    return sha1(value.encode('utf-8', errors='ignore')).hexdigest()[:8]


@projects_bp.get('/projects')
def list_projects():
    items = []

    before_after = BeforeAfterProject.query.filter(
        BeforeAfterProject.is_published.isnot(False)
    ).order_by(BeforeAfterProject.created_at.desc()).all()

    for p in before_after:
        items.append({
            'id': f"before-after-{p.id}",
            'source': 'before-after',
            'title': p.title,
            'description': p.description,
            'summary': p.description,
            'image_url': p.after_poster_url or p.before_poster_url,
            'image_url_token': _media_token(p.after_poster_url or p.before_poster_url),
            'video_url': p.after_video_url or p.before_video_url,
            'video_url_token': _media_token(p.after_video_url or p.before_video_url),
            'category': p.category,
            'room_type': p.room_type,
            'location': p.room_type,
            'status': p.status,
            'is_published': p.is_published,
            'created_at': p.created_at.isoformat() if p.created_at else None,
            'updated_at': p.updated_at.isoformat() if p.updated_at else None,
        })

    portfolio = PortfolioProject.query.filter(
        PortfolioProject.is_published.isnot(False)
    ).order_by(PortfolioProject.created_at.desc()).all()

    for p in portfolio:
        items.append({
            'id': f"portfolio-{p.id}",
            'source': 'portfolio',
            'title': p.title,
            'description': p.description,
            'summary': p.summary,
            'image_url': p.image_url,
            'image_url_token': _media_token(p.image_url),
            'video_url': p.video_url,
            'video_url_token': _media_token(p.video_url),
            'category': p.category,
            'room_type': p.room_type,
            'location': p.location,
            'status': p.status,
            'is_published': p.is_published,
            'created_at': p.created_at.isoformat() if p.created_at else None,
            'updated_at': p.updated_at.isoformat() if p.updated_at else None,
        })

    items.sort(key=lambda x: x.get('created_at') or '', reverse=True)
    return jsonify(items), 200
