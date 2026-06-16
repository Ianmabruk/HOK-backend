from flask import Blueprint, request, jsonify
import uuid
from models.models import db, Product, ProductVariant
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


def _clean_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _clean_json_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = __import__('json').loads(text)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


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


def _variant_payload(row, index, product_id):
    color_name = _clean_text(row.get('colorName', row.get('color_name'))) or 'Custom Color'
    hex_color = _clean_text(row.get('hexColor', row.get('hex_color'))) or '#000000'
    image_url = _clean_text(row.get('imageUrl', row.get('image_url')))
    stock_quantity = _safe_int(row.get('stockQuantity', row.get('stock_quantity', row.get('stock', 0))), 0)
    price_override = row.get('priceOverride', row.get('price_override'))
    return {
        'id': row.get('id') or row.get('variantId'),
        'product_id': product_id,
        'color_name': color_name,
        'hex_color': hex_color,
        'image_url': image_url,
        'price_override': _safe_float(price_override) if price_override not in (None, '') else None,
        'stock_quantity': stock_quantity,
        'active_status': _clean_bool(row.get('activeStatus', row.get('active_status')), True),
        'is_default': _clean_bool(row.get('isDefault', row.get('is_default')), False),
        'sort_order': _safe_int(row.get('sortOrder', row.get('sort_order')), index),
        'variant_sku': _clean_text(row.get('variantSku', row.get('variant_sku'))),
    }


def _sync_product_variants(product, raw_variants):
    if not isinstance(raw_variants, list):
        return

    incoming = [_variant_payload(row, index, product.id) for index, row in enumerate(raw_variants)]
    incoming.sort(key=lambda item: item['sort_order'])

    if incoming:
        has_default = any(item['is_default'] for item in incoming)
        if not has_default:
            incoming[0]['is_default'] = True
        else:
            first_default_seen = False
            for item in incoming:
                if item['is_default'] and not first_default_seen:
                    first_default_seen = True
                elif item['is_default']:
                    item['is_default'] = False

    existing_by_id = {str(variant.id): variant for variant in product.variants}
    incoming_ids = {str(item['id']) for item in incoming if item.get('id')}

    for item in incoming:
        variant_id = item.pop('id', None)
        variant = existing_by_id.get(str(variant_id)) if variant_id else None
        if variant is None:
            variant = ProductVariant(product_id=product.id)
            db.session.add(variant)
        variant.color_name = item['color_name']
        variant.hex_color = item['hex_color']
        variant.image_url = item['image_url']
        variant.price_override = item['price_override']
        variant.stock_quantity = item['stock_quantity']
        variant.active_status = item['active_status']
        variant.is_default = item['is_default']
        variant.sort_order = item['sort_order']
        variant.variant_sku = item['variant_sku']

    for variant_id, variant in existing_by_id.items():
        if variant_id not in incoming_ids:
            db.session.delete(variant)


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
    featured = request.args.get('featured')
    trending = request.args.get('trending')

    q = Product.query.filter(
        Product.price >= price_min,
        Product.price <= price_max
    )
    if featured is not None:
        featured_val = _clean_bool(featured, False)
        q = q.filter(Product.featured == featured_val)
    if trending is not None:
        trending_val = _clean_bool(trending, False)
        q = q.filter(Product.trending == trending_val)
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


@products_bp.get('/products/categories')
def get_products_categories():
    """Get unique product categories for shop navigation."""
    categories = db.session.execute(
        text('SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != \'\' ORDER BY category ASC')
    ).mappings().all()
    return jsonify([cat['category'] for cat in categories])


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
        'display_price': _safe_float(data.get('display_price')) or price,
        'price_usd': _safe_float(data.get('price_usd')) or price,
        'base_currency': _clean_text(data.get('base_currency')) or 'USD',
        'sku': _clean_text(data.get('sku')),
        'status': _clean_text(data.get('status')) or 'in-stock',
        'category': _normalize_category(data.get('category')) or None,
        'subcategory': _clean_text(data.get('subcategory')),
        'image_url': _clean_text(data.get('image_url')),
        'video_url': _clean_text(data.get('video_url')),
        'vendor_id': vendor_id,
        'featured': _clean_bool(data.get('featured'), False),
        'trending': _clean_bool(data.get('trending'), False),
        'tags': _clean_json_list(data.get('tags')),
        'material_type': _clean_text(data.get('material_type')),
        'color_theme': _clean_text(data.get('color_theme')),
        'dimensions': _clean_text(data.get('dimensions')),
        'variants': data.get('variants') if isinstance(data.get('variants'), list) else [],
    }

    try:
        p = Product(
            title=payload['title'],
            description=payload['description'],
            price=payload['price'],
            stock=payload['stock'],
            cost_price=payload['cost_price'],
            display_price=payload['display_price'],
            price_usd=payload['price_usd'],
            base_currency=payload['base_currency'],
            sku=payload['sku'],
            status=payload['status'],
            category=payload['category'],
            subcategory=payload['subcategory'],
            image_url=payload['image_url'],
            video_url=payload['video_url'],
            vendor_id=payload['vendor_id'],
            featured=payload['featured'],
            trending=payload['trending'],
            tags=payload['tags'],
            material_type=payload['material_type'],
            color_theme=payload['color_theme'],
            dimensions=payload['dimensions'],
        )
        db.session.add(p)
        db.session.commit()
        _sync_product_variants(p, payload['variants'])
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

    if 'display_price' in data:
        p.display_price = _safe_float(data.get('display_price'))
    if 'price_usd' in data:
        p.price_usd = _safe_float(data.get('price_usd'))
    if 'base_currency' in data:
        p.base_currency = _clean_text(data.get('base_currency')) or 'USD'
    if 'sku' in data:
        p.sku = _clean_text(data.get('sku'))
    if 'status' in data:
        p.status = _clean_text(data.get('status')) or 'in-stock'
    if 'subcategory' in data:
        p.subcategory = _clean_text(data.get('subcategory'))

    if 'stock' in data:
        stock = _safe_int(data.get('stock'), None)
        if stock is None or stock < 0:
            return jsonify({'error': 'Invalid input', 'field': 'stock', 'message': 'Stock must be a valid non-negative integer'}), 400
        p.stock = stock

    if 'vendor_id' in data:
        p.vendor_id = _normalize_vendor_id(data.get('vendor_id'))

    if 'category' in data:
        p.category = _normalize_category(data.get('category')) or None

    if 'featured' in data:
        p.featured = _clean_bool(data.get('featured'), False)
    if 'trending' in data:
        p.trending = _clean_bool(data.get('trending'), False)
    if 'tags' in data:
        p.tags = _clean_json_list(data.get('tags'))
    if 'material_type' in data:
        p.material_type = _clean_text(data.get('material_type'))
    if 'color_theme' in data:
        p.color_theme = _clean_text(data.get('color_theme'))
    if 'dimensions' in data:
        p.dimensions = _clean_text(data.get('dimensions'))

    try:
        db.session.commit()
        if isinstance(data.get('variants'), list):
            _sync_product_variants(p, data.get('variants'))
        db.session.commit()
        return jsonify(p.to_dict())
    except Exception:
        db.session.rollback()
        logger.exception('Failed to update product id=%s', pid)
        return jsonify({'error': 'Unexpected server error', 'message': 'Could not update product'}), 500


@products_bp.get('/products/<uuid:pid>/variants')
def get_product_variants(pid):
    p = Product.query.get_or_404(pid)
    return jsonify([variant.to_dict() for variant in p.variants])


@products_bp.post('/products/<uuid:pid>/variants')
@jwt_required()
def create_product_variant(pid):
    err = admin_required()
    if err:
        return err
    p = Product.query.get_or_404(pid)
    data = request.get_json(silent=True) or {}
    existing_variants = [variant.to_dict() for variant in p.variants]
    _sync_product_variants(p, [*existing_variants, {**data, 'sortOrder': data.get('sortOrder', len(p.variants))}])
    db.session.commit()
    return jsonify(p.to_dict()), 201


@products_bp.put('/products/<uuid:pid>/variants/<uuid:variant_id>')
@jwt_required()
def update_product_variant(pid, variant_id):
    err = admin_required()
    if err:
        return err
    p = Product.query.get_or_404(pid)
    variant = ProductVariant.query.filter_by(id=variant_id, product_id=p.id).first_or_404()
    data = request.get_json(silent=True) or {}
    payload = {
        'id': str(variant.id),
        'colorName': data.get('colorName', data.get('color_name', variant.color_name)),
        'hexColor': data.get('hexColor', data.get('hex_color', variant.hex_color)),
        'imageUrl': data.get('imageUrl', data.get('image_url', variant.image_url)),
        'priceOverride': data.get('priceOverride', data.get('price_override', variant.price_override)),
        'stockQuantity': data.get('stockQuantity', data.get('stock_quantity', variant.stock_quantity)),
        'activeStatus': data.get('activeStatus', data.get('active_status', variant.active_status)),
        'isDefault': data.get('isDefault', data.get('is_default', variant.is_default)),
        'sortOrder': data.get('sortOrder', data.get('sort_order', variant.sort_order)),
        'variantSku': data.get('variantSku', data.get('variant_sku', variant.variant_sku)),
    }
    existing_variants = [item for item in [variant.to_dict() for variant in p.variants] if str(item['id']) != str(variant_id)]
    _sync_product_variants(p, [*existing_variants, payload])
    db.session.commit()
    return jsonify(variant.to_dict()), 200


@products_bp.delete('/products/<uuid:pid>/variants/<uuid:variant_id>')
@jwt_required()
def delete_product_variant(pid, variant_id):
    err = admin_required()
    if err:
        return err
    p = Product.query.get_or_404(pid)
    variant = ProductVariant.query.filter_by(id=variant_id, product_id=p.id).first_or_404()
    db.session.delete(variant)
    db.session.commit()
    return jsonify({'message': 'Deleted'})


@products_bp.patch('/products/<uuid:pid>/variants/reorder')
@jwt_required()
def reorder_product_variants(pid, variant_id=None):
    err = admin_required()
    if err:
        return err
    p = Product.query.get_or_404(pid)
    data = request.get_json(silent=True) or {}
    variant_ids = data.get('variantIds') or data.get('variant_ids') or []
    if not isinstance(variant_ids, list):
        return jsonify({'message': 'variantIds must be a list'}), 400
    variants = ProductVariant.query.filter(ProductVariant.id.in_(variant_ids), ProductVariant.product_id == p.id).all()
    if len(variants) != len(set(str(v.id) for v in variants)):
        return jsonify({'message': 'Duplicate variant ids'}), 400
    for index, variant in enumerate(variants):
        variant.sort_order = index
        variant.is_default = index == 0
    db.session.commit()
    return jsonify([variant.to_dict() for variant in variants]), 200


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
