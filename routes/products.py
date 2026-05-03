from flask import Blueprint, request, jsonify
from models.models import db, Product
from flask_jwt_extended import jwt_required
from sqlalchemy import func, or_
import re

from auth_utils import current_user_role
from services.media_storage import save_media_file

products_bp = Blueprint('products', __name__)


def _normalize_category(value):
    normalized = (value or '').strip().lower().replace('_', '-')
    normalized = re.sub(r'\s+', '-', normalized)
    normalized = re.sub(r'-+', '-', normalized)
    return normalized.strip('-')


def admin_required():
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    return None


@products_bp.get('/products')
def get_products():
    category = _normalize_category(request.args.get('category'))
    search = request.args.get('search')
    sort = request.args.get('sort', '')
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 12))
    price_min = request.args.get('price_min', 0, type=float)
    price_max = request.args.get('price_max', 1e9, type=float)

    q = Product.query.filter(
        Product.price >= price_min,
        Product.price <= price_max
    )
    if category:
        normalized_category = func.lower(
            func.replace(
                func.replace(
                    func.trim(Product.category),
                    ' ',
                    '-',
                ),
                '_',
                '-',
            )
        )
        q = q.filter(normalized_category == category)
    if search:
        q = q.filter(or_(
            Product.title.ilike(f'%{search}%'),
            Product.description.ilike(f'%{search}%')
        ))
    if sort == 'price_asc':
        q = q.order_by(Product.price.asc())
    elif sort == 'price_desc':
        q = q.order_by(Product.price.desc())
    elif sort == 'newest':
        q = q.order_by(Product.created_at.desc())
    else:
        q = q.order_by(Product.id.desc())

    total = q.count()
    products = q.offset((page - 1) * limit).limit(limit).all()
    return jsonify({'products': [p.to_dict() for p in products], 'total': total})


@products_bp.get('/products/<int:pid>')
def get_product(pid):
    p = Product.query.get_or_404(pid)
    return jsonify(p.to_dict())


@products_bp.post('/products')
@jwt_required()
def create_product():
    err = admin_required()
    if err:
        return err
    data = request.get_json()
    p = Product(
        title=data['title'], description=data.get('description'),
        price=data['price'], stock=data.get('stock', 0),
        category=_normalize_category(data.get('category')) or None, image_url=data.get('image_url'),
        video_url=data.get('video_url'), vendor_id=data.get('vendor_id') or None
    )
    db.session.add(p)
    db.session.commit()
    return jsonify(p.to_dict()), 201


@products_bp.put('/products/<int:pid>')
@jwt_required()
def update_product(pid):
    err = admin_required()
    if err:
        return err
    p = Product.query.get_or_404(pid)
    data = request.get_json()
    for field in ('title', 'description', 'price', 'stock', 'image_url', 'video_url', 'vendor_id'):
        if field in data:
            setattr(p, field, data[field] if data[field] != '' else None)
    if 'category' in data:
        p.category = _normalize_category(data.get('category')) or None
    db.session.commit()
    return jsonify(p.to_dict())


@products_bp.post('/products/media-upload')
@jwt_required()
def upload_product_media():
    err = admin_required()
    if err:
        return err

    media_kind = request.form.get('type', 'image').strip().lower()
    if media_kind not in {'image', 'video'}:
        return jsonify({'message': 'Invalid media type'}), 400

    file = request.files.get('file')
    if not file:
        return jsonify({'message': 'No file uploaded'}), 400

    try:
        uploaded = save_media_file(file, media_kind)
    except ValueError as exc:
        return jsonify({'message': str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({'message': str(exc)}), 500

    return jsonify(uploaded), 201


@products_bp.delete('/products/<int:pid>')
@jwt_required()
def delete_product(pid):
    err = admin_required()
    if err:
        return err
    p = Product.query.get_or_404(pid)
    # Nullify FK references in order_items so the delete doesn't fail
    from models.models import OrderItem
    OrderItem.query.filter_by(product_id=pid).update({'product_id': None})
    db.session.delete(p)
    db.session.commit()
    return jsonify({'message': 'Deleted'})
