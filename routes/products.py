from flask import Blueprint, request, jsonify
import uuid
from models.models import db, Product
from flask_jwt_extended import jwt_required
from sqlalchemy import func, inspect, or_, text
import re
import logging
from datetime import datetime

from auth_utils import current_user_role
from services.media_storage import MediaUploadError, save_media_file

products_bp = Blueprint('products', __name__)
logger = logging.getLogger(__name__)


def _safe_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _safe_int(value, default=0):
    try:
        if value is None or value == '':
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value, default=None):
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def _clean_text(value):
    return str(value or '').strip() or None


def _normalize_vendor_id(value):
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return value


def _normalize_category(value):
    normalized = (value or '').strip().lower().replace('_', '-')
    normalized = re.sub(r'\s+', '-', normalized)
    normalized = re.sub(r'-+', '-', normalized)
    return normalized.strip('-')


def admin_required():
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    return None


@products_bp.post('/products/media-upload')
@jwt_required()
def upload_product_media():
    err = admin_required()
    if err:
        return err

    media_type = str(request.form.get('type') or 'image').strip().lower()
    file = request.files.get('file')
    if file is None or not file.filename:
        return jsonify({'message': 'Missing file'}), 400
    if media_type not in {'image', 'video'}:
        return jsonify({'message': 'Invalid media type'}), 400

    folder = request.form.get('folder') or ('products/videos' if media_type == 'video' else 'products/images')
    try:
        uploaded = save_media_file(file, media_type, folder=folder)
        return jsonify({
            'url': uploaded['url'],
            'public_url': uploaded['url'],
            'path': uploaded.get('public_id'),
            'public_id': uploaded.get('public_id'),
            'bucket': uploaded.get('bucket'),
            'media_type': media_type,
            'content_type': uploaded.get('content_type'),
        }), 201
    except MediaUploadError as exc:
        return jsonify({'message': exc.user_message, 'error': str(exc)}), exc.status_code


@products_bp.get('/products')
def get_products():
    category = _normalize_category(request.args.get('category'))
    search = request.args.get('search')
    sort = request.args.get('sort', '')
    page = max(_safe_int(request.args.get('page'), 1), 1)
    limit = min(max(_safe_int(request.args.get('limit'), 12), 1), 200)
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


@products_bp.get('/products/<uuid:pid>')
def get_product(pid):
    p = Product.query.get_or_404(pid)
    return jsonify(p.to_dict())


@products_bp.post('/products')
@jwt_required()
def create_product():
    err = admin_required()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    title = _clean_text(data.get('title'))
    if not title:
        return jsonify({'error': 'Invalid input', 'field': 'title', 'message': 'Title is required'}), 400

    price = _safe_float(data.get('price'))
    if price is None or price < 0:
        return jsonify({'error': 'Invalid input', 'field': 'price', 'message': 'Price must be a valid non-negative number'}), 400

    stock = _safe_int(data.get('stock'), 0)
    if stock < 0:
        return jsonify({'error': 'Invalid input', 'field': 'stock', 'message': 'Stock cannot be negative'}), 400

    cost_price = _safe_float(data.get('cost_price'))
    vendor_id = _normalize_vendor_id(data.get('vendor_id'))

    payload = {
        'title': title,
        'description': _clean_text(data.get('description')),
        'price': price,
        'stock': stock,
        'cost_price': cost_price,
        'category': _normalize_category(data.get('category')) or None,
        'image_url': _clean_text(data.get('image_url')),
        'video_url': _clean_text(data.get('video_url')),
        'vendor_id': vendor_id,
    }

    try:
        p = Product(
            title=payload['title'],
            description=payload['description'],
            price=payload['price'],
            stock=payload['stock'],
            cost_price=payload['cost_price'],
            category=payload['category'],
            image_url=payload['image_url'],
            video_url=payload['video_url'],
            vendor_id=payload['vendor_id'],
        )
        db.session.add(p)
        db.session.commit()
        return jsonify(p.to_dict()), 201
    except Exception as exc:
        db.session.rollback()
        logger.exception('ORM create failed; trying raw SQL fallback: %s', exc)

        try:
            column_defs = inspect(db.engine).get_columns('products')
            insert_values = {}

            for col in column_defs:
                name = col.get('name')
                if name == 'id' and col.get('nullable', True) is False and col.get('default') is None:
                    type_name = str(col.get('type') or '').lower()
                    if 'uuid' in type_name:
                        insert_values['id'] = str(uuid.uuid4())
                if name in payload:
                    insert_values[name] = payload[name]

            for col in column_defs:
                name = col.get('name')
                if not name or name in insert_values:
                    continue
                if col.get('nullable', True):
                    continue
                if col.get('default') is not None:
                    continue

                type_name = str(col.get('type') or '').lower()
                if 'bool' in type_name:
                    insert_values[name] = False
                elif any(t in type_name for t in ('int', 'numeric', 'decimal', 'float', 'double')):
                    insert_values[name] = 0
                elif 'date' in type_name or 'time' in type_name:
                    insert_values[name] = datetime.utcnow()
                else:
                    insert_values[name] = ''

            sql_cols = ', '.join(insert_values.keys())
            sql_params = ', '.join(f':{k}' for k in insert_values.keys())
            dialect = db.session.bind.dialect.name if db.session.bind is not None else ''
            returning_clause = ' RETURNING id' if dialect == 'postgresql' else ''
            result = db.session.execute(
                text(f'INSERT INTO products ({sql_cols}) VALUES ({sql_params}){returning_clause}'),
                insert_values,
            )
            new_id = result.scalar() if returning_clause else None
            db.session.commit()
            return jsonify({'id': str(new_id) if new_id is not None else None, 'message': 'Product created successfully'}), 201
        except Exception as fallback_exc:
            db.session.rollback()
            logger.exception('Raw SQL fallback failed for create product: %s', fallback_exc)
            return jsonify({'error': 'Unexpected server error', 'message': 'Could not create product', 'details': str(fallback_exc)}), 500


@products_bp.put('/products/<uuid:pid>')
@jwt_required()
def update_product(pid):
    err = admin_required()
    if err:
        return err
    p = Product.query.get_or_404(pid)
    data = request.get_json(silent=True) or {}

    if 'title' in data:
        title = _clean_text(data.get('title'))
        if not title:
            return jsonify({'error': 'Invalid input', 'field': 'title', 'message': 'Title cannot be empty'}), 400
        p.title = title

    if 'description' in data:
        p.description = _clean_text(data.get('description'))
    if 'image_url' in data:
        p.image_url = _clean_text(data.get('image_url'))
    if 'video_url' in data:
        p.video_url = _clean_text(data.get('video_url'))

    if 'price' in data:
        price = _safe_float(data.get('price'))
        if price is None or price < 0:
            return jsonify({'error': 'Invalid input', 'field': 'price', 'message': 'Price must be a valid non-negative number'}), 400
        p.price = price

    if 'cost_price' in data:
        cost_price = _safe_float(data.get('cost_price'))
        if data.get('cost_price') not in (None, '') and cost_price is None:
            return jsonify({'error': 'Invalid input', 'field': 'cost_price', 'message': 'cost_price must be a valid number'}), 400
        p.cost_price = cost_price

    if 'stock' in data:
        stock = _safe_int(data.get('stock'), None)
        if stock is None or stock < 0:
            return jsonify({'error': 'Invalid input', 'field': 'stock', 'message': 'Stock must be a valid non-negative integer'}), 400
        p.stock = stock

    if 'vendor_id' in data:
        p.vendor_id = _normalize_vendor_id(data.get('vendor_id'))

    if 'category' in data:
        p.category = _normalize_category(data.get('category')) or None

    try:
        db.session.commit()
        return jsonify(p.to_dict())
    except Exception:
        db.session.rollback()
        logger.exception('Failed to update product id=%s', pid)
        return jsonify({'error': 'Unexpected server error', 'message': 'Could not update product'}), 500


@products_bp.delete('/products/<uuid:pid>')
@jwt_required()
def delete_product(pid):
    err = admin_required()
    if err:
        return err
    p = Product.query.get_or_404(pid)
    from models.models import OrderItem, WishlistItem
    # Remove order items and wishlist entries that reference this product
    OrderItem.query.filter_by(product_id=pid).delete(synchronize_session='fetch')
    WishlistItem.query.filter_by(product_id=pid).delete(synchronize_session='fetch')
    db.session.delete(p)
    db.session.commit()
    return jsonify({'message': 'Deleted'})
