from copy import deepcopy

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from auth_utils import current_user_role
from models.models import SiteSetting, db

site_settings_bp = Blueprint('site_settings', __name__)

DEFAULT_LANDING_IMAGES = {
    'hero': 'https://images.unsplash.com/photo-1618219908412-a29a1bb7b86e?w=1800&q=85',
    'categories': {
        'living-room': 'https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=600&q=80',
        'bedroom': 'https://images.unsplash.com/photo-1560448204-603b3fc33ddc?w=600&q=80',
        'kitchen': 'https://images.unsplash.com/photo-1560185007-5f0bb1866cab?w=600&q=80',
        'office': 'https://images.unsplash.com/photo-1524758631624-e2822e304c36?w=600&q=80',
        'dining': 'https://images.unsplash.com/photo-1617806118233-18e1de247200?w=600&q=80',
        'outdoor': 'https://images.unsplash.com/photo-1600210492493-0946911123ea?w=600&q=80',
    },
}


def _require_admin():
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    return None


def _merge_landing_images(value):
    merged = deepcopy(DEFAULT_LANDING_IMAGES)
    if not isinstance(value, dict):
        return merged

    hero = value.get('hero')
    if isinstance(hero, str) and hero.strip():
        merged['hero'] = hero.strip()

    categories = value.get('categories')
    if isinstance(categories, dict):
        for slug in merged['categories'].keys():
            url = categories.get(slug)
            if isinstance(url, str) and url.strip():
                merged['categories'][slug] = url.strip()

    return merged


def _get_landing_images():
    setting = SiteSetting.query.filter_by(key='landing_images').first()
    if not setting:
        return deepcopy(DEFAULT_LANDING_IMAGES)
    return _merge_landing_images(setting.value)


@site_settings_bp.get('/site-settings/landing-images')
def get_landing_images():
    return jsonify(_get_landing_images()), 200


@site_settings_bp.put('/site-settings/landing-images')
@jwt_required()
def update_landing_images():
    err = _require_admin()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    merged = _merge_landing_images(data)

    setting = SiteSetting.query.filter_by(key='landing_images').first()
    if not setting:
        setting = SiteSetting(key='landing_images', value=merged)
        db.session.add(setting)
    else:
        setting.value = merged

    db.session.commit()
    return jsonify(merged), 200
