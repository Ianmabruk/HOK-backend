from flask import Blueprint, request, jsonify
from models.models import db, Product
from flask_jwt_extended import jwt_required
from sqlalchemy import or_

from auth_utils import current_user_role

products_bp = Blueprint('products', __name__)


def admin_required():
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    return None


@products_bp.get('/products')
def get_products():
    category = request.args.get('category')
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
        q = q.filter_by(category=category)
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
        category=data.get('category'), image_url=data.get('image_url'),
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
    for field in ('title', 'description', 'price', 'stock', 'category', 'image_url', 'video_url', 'vendor_id'):
        if field in data:
            setattr(p, field, data[field] if data[field] != '' else None)
    db.session.commit()
    return jsonify(p.to_dict())


@products_bp.delete('/products/<int:pid>')
@jwt_required()
def delete_product(pid):
    err = admin_required()
    if err:
        return err
    p = Product.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    return jsonify({'message': 'Deleted'})
