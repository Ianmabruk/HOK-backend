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

DEFAULT_CATEGORY_SHOWCASE = {
    'sections': {
        'homeCategoryShowcase': True,
        'virtualShowcase': True,
    },
    'categories': [
        {
            'slug': 'living-room',
            'title': 'Living Room',
            'description': 'Sofas, accent pieces, and elevated lounge essentials.',
            'iconKey': 'FaCouch',
            'bannerUrl': 'https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=1200&q=80',
            'enabled': True,
            'featuredOrder': 1,
        },
        {
            'slug': 'bedroom',
            'title': 'Bedroom',
            'description': 'Calm textures, premium bedding, and restorative comfort.',
            'iconKey': 'FaHome',
            'bannerUrl': 'https://images.unsplash.com/photo-1560448204-603b3fc33ddc?w=1200&q=80',
            'enabled': True,
            'featuredOrder': 2,
        },
        {
            'slug': 'kitchen',
            'title': 'Kitchen',
            'description': 'Functional layouts with modern finishes and smart details.',
            'iconKey': 'FaLayerGroup',
            'bannerUrl': 'https://images.unsplash.com/photo-1560185007-5f0bb1866cab?w=1200&q=80',
            'enabled': True,
            'featuredOrder': 3,
        },
        {
            'slug': 'office',
            'title': 'Office',
            'description': 'Workspaces designed for focus, style, and flow.',
            'iconKey': 'FaBoxOpen',
            'bannerUrl': 'https://images.unsplash.com/photo-1524758631624-e2822e304c36?w=1200&q=80',
            'enabled': True,
            'featuredOrder': 4,
        },
        {
            'slug': 'dining',
            'title': 'Dining',
            'description': 'Gathering spaces with timeless tables and statement seating.',
            'iconKey': 'FaPalette',
            'bannerUrl': 'https://images.unsplash.com/photo-1617806118233-18e1de247200?w=1200&q=80',
            'enabled': True,
            'featuredOrder': 5,
        },
        {
            'slug': 'outdoor',
            'title': 'Outdoor',
            'description': 'Weather-ready furniture and open-air living upgrades.',
            'iconKey': 'FaCube',
            'bannerUrl': 'https://images.unsplash.com/photo-1600210492493-0946911123ea?w=1200&q=80',
            'enabled': True,
            'featuredOrder': 6,
        },
    ],
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


def _normalize_slug(value):
    return str(value or '').strip().lower()


def _merge_category_showcase(value):
    merged = deepcopy(DEFAULT_CATEGORY_SHOWCASE)
    if not isinstance(value, dict):
        return merged

    sections = value.get('sections')
    if isinstance(sections, dict):
        for key in merged['sections'].keys():
            incoming = sections.get(key)
            if isinstance(incoming, bool):
                merged['sections'][key] = incoming

    incoming_categories = value.get('categories')
    if isinstance(incoming_categories, list):
        default_map = {_normalize_slug(item.get('slug')): item for item in merged['categories']}
        normalized = []
        for index, item in enumerate(incoming_categories):
            if not isinstance(item, dict):
                continue
            slug = _normalize_slug(item.get('slug'))
            if not slug:
                continue

            base = deepcopy(default_map.get(slug, {
                'slug': slug,
                'title': slug.replace('-', ' ').title(),
                'description': '',
                'iconKey': 'FaLayerGroup',
                'bannerUrl': '',
                'enabled': True,
                'featuredOrder': index + 1,
            }))
            for key in ('title', 'description', 'iconKey', 'bannerUrl'):
                incoming = item.get(key)
                if isinstance(incoming, str):
                    base[key] = incoming.strip()

            enabled = item.get('enabled')
            if isinstance(enabled, bool):
                base['enabled'] = enabled

            featured_order = item.get('featuredOrder')
            if isinstance(featured_order, int):
                base['featuredOrder'] = featured_order
            else:
                base['featuredOrder'] = index + 1

            base['slug'] = slug
            normalized.append(base)

        if normalized:
            normalized.sort(key=lambda item: item.get('featuredOrder', 0))
            merged['categories'] = normalized

    return merged


def _get_category_showcase():
    setting = SiteSetting.query.filter_by(key='category_showcase').first()
    if not setting:
        return deepcopy(DEFAULT_CATEGORY_SHOWCASE)
    return _merge_category_showcase(setting.value)


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


@site_settings_bp.get('/site-settings/category-showcase')
def get_category_showcase():
    return jsonify(_get_category_showcase()), 200


@site_settings_bp.put('/site-settings/category-showcase')
@jwt_required()
def update_category_showcase():
    err = _require_admin()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    merged = _merge_category_showcase(data)

    setting = SiteSetting.query.filter_by(key='category_showcase').first()
    if not setting:
        setting = SiteSetting(key='category_showcase', value=merged)
        db.session.add(setting)
    else:
        setting.value = merged

    db.session.commit()
    return jsonify(merged), 200
