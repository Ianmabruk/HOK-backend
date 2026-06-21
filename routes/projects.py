"""
Projects route - combines portfolio and before-after projects.
GET /api/projects - list published projects from both sources
"""
import logging
from hashlib import sha1

from flask import Blueprint, jsonify
from models.models import BeforeAfterProject, PortfolioProject, db

projects_bp = Blueprint('projects', __name__)
logger = logging.getLogger(__name__)


def _media_token(value):
    value = str(value or '').strip()
    if not value:
        return ''
    return sha1(value.encode('utf-8', errors='ignore')).hexdigest()[:8]


def _get_updated_at(model_instance):
    try:
        return model_instance.updated_at
    except Exception:
        return None


def _safe_iso(dt):
    try:
        return dt.isoformat() if dt else None
    except Exception:
        return None


@projects_bp.get('/projects')
def list_projects():
    try:
        items = []

        try:
            before_after = (
                BeforeAfterProject.query
                .filter(BeforeAfterProject.is_published.isnot(False))
                .order_by(BeforeAfterProject.created_at.desc())
                .all()
            )
        except Exception as exc:
            logger.warning('Failed to load before_after_projects: %s', exc)
            before_after = []

        for p in before_after:
            image_url = p.after_poster_url or p.before_poster_url
            video_url = p.after_video_url or p.before_video_url
            items.append({
                'id': f"before-after-{p.id}",
                'source': 'before-after',
                'title': p.title,
                'description': p.description,
                'summary': p.description,
                'image_url': image_url,
                'image_url_token': _media_token(image_url),
                'video_url': video_url,
                'video_url_token': _media_token(video_url),
                'category': p.category,
                'room_type': p.room_type,
                'location': p.room_type,
                'status': p.status,
                'is_published': p.is_published,
                'created_at': _safe_iso(p.created_at),
                'updated_at': _safe_iso(_get_updated_at(p)),
            })

        try:
            portfolio = (
                PortfolioProject.query
                .filter(PortfolioProject.is_published.isnot(False))
                .order_by(PortfolioProject.created_at.desc())
                .all()
            )
        except Exception as exc:
            logger.warning('Failed to load portfolio_projects: %s', exc)
            portfolio = []

        for p in portfolio:
            image_url = p.image_url
            video_url = p.video_url
            items.append({
                'id': f"portfolio-{p.id}",
                'source': 'portfolio',
                'title': p.title,
                'description': p.description,
                'summary': p.summary,
                'image_url': image_url,
                'image_url_token': _media_token(image_url),
                'video_url': video_url,
                'video_url_token': _media_token(video_url),
                'category': p.category,
                'room_type': p.room_type,
                'location': p.location,
                'status': p.status,
                'is_published': p.is_published,
                'created_at': _safe_iso(p.created_at),
                'updated_at': _safe_iso(_get_updated_at(p)),
            })

        items.sort(key=lambda x: x.get('created_at') or '', reverse=True)
        return jsonify(items), 200
    except Exception as exc:
        logger.exception('GET /projects failed: %s', exc)
        return jsonify([]), 200
