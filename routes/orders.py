import logging

from flask import Blueprint, request, jsonify
from models.models import db, Order, OrderItem, Product
from flask_jwt_extended import jwt_required

from auth_utils import current_user_id, current_user_role
from services.email_service import send_order_confirmation_email

orders_bp = Blueprint('orders', __name__)
logger = logging.getLogger(__name__)


@orders_bp.post('/orders')
@jwt_required()
def create_order():
    data = request.get_json() or {}
    items_data = data.get('items', [])
    if not items_data:
        return jsonify({'message': 'No items'}), 400

    shipping_info = data.get('shipping_info', {})
    if not isinstance(shipping_info, dict):
        shipping_info = {}
    payment_method = str(shipping_info.get('payment_method') or '').strip().lower()
    is_quote_request = payment_method == 'quote'

    order = Order(
        user_id=current_user_id(),
        total_price=data.get('total_price', 0),
        status='quote_requested' if is_quote_request else 'pending',
        shipping_info=shipping_info,
    )
    db.session.add(order)
    db.session.flush()

    for idx, item in enumerate(items_data, start=1):
        if not isinstance(item, dict):
            db.session.rollback()
            return jsonify({'message': f'Invalid order item at position {idx}'}), 400

        product_id = item.get('product_id')
        quantity = item.get('quantity')
        if product_id is None or quantity is None:
            db.session.rollback()
            return jsonify({'message': f'Order item #{idx} is missing product_id or quantity'}), 400

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            db.session.rollback()
            return jsonify({'message': f'Order item #{idx} has invalid quantity'}), 400

        if quantity <= 0:
            db.session.rollback()
            return jsonify({'message': f'Order item #{idx} quantity must be at least 1'}), 400

        product = Product.query.get(product_id)
        if not product:
            db.session.rollback()
            return jsonify({'message': f'Product {product_id} not found'}), 400
        if not is_quote_request and product.stock < quantity:
            db.session.rollback()
            return jsonify({'message': f'Insufficient stock for product {product_id}'}), 400

        if not is_quote_request:
            product.stock -= quantity

        oi = OrderItem(
            order_id=order.id,
            product_id=product_id,
            quantity=quantity,
            unit_price=product.price,
            product_title=product.title,
            product_image=product.image_url,
            customizations=item.get('customizations') if isinstance(item, dict) else None,
        )
        db.session.add(oi)

    db.session.commit()

    customer_email = (shipping_info.get('email') or (order.user.email if order.user else '') or '').strip()
    customer_name = ' '.join([
        str(shipping_info.get('first_name') or '').strip(),
        str(shipping_info.get('last_name') or '').strip(),
    ]).strip() or (order.user.name if order.user else 'there')

    if customer_email:
        try:
            currency_code = str(shipping_info.get('currency') or 'USD').upper()
            currency_symbols = {'KES': 'KSh', 'USD': '$', 'NGN': '\u20a6'}
            currency_symbol = currency_symbols.get(currency_code, '$')
            send_order_confirmation_email(
                to_email=customer_email,
                name=customer_name,
                order_id=order.id,
                total_price=float(order.total_price or 0),
                items=[item.to_dict() for item in order.items],
                shipping_info=shipping_info,
                is_quote_request=is_quote_request,
                currency_symbol=currency_symbol,
                currency_code=currency_code,
            )
        except Exception:
            logger.exception('Order confirmation email dispatch failed for order_id=%s', order.id)

    return jsonify(order.to_dict()), 201


@orders_bp.get('/orders')
@jwt_required()
def get_orders():
    if current_user_role() == 'admin':
        orders = Order.query.order_by(Order.created_at.desc()).all()
    else:
        orders = Order.query.filter_by(user_id=current_user_id()).order_by(Order.created_at.desc()).all()
    return jsonify([o.to_dict() for o in orders])


@orders_bp.put('/orders/<int:oid>/status')
@jwt_required()
def update_status(oid):
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    order = Order.query.get_or_404(oid)
    data = request.get_json()
    allowed = ('quote_requested', 'pending', 'shipped', 'delivered', 'cancelled')
    if data.get('status') not in allowed:
        return jsonify({'message': 'Invalid status'}), 400
    order.status = data['status']
    db.session.commit()
    return jsonify(order.to_dict())
