import logging
import uuid
import json

from flask import Blueprint, request, jsonify
from sqlalchemy import text, inspect
from models.models import db, Order, OrderItem, Product, User
from flask_jwt_extended import jwt_required

from auth_utils import current_user_id, current_user_role
from services.email_service import send_order_confirmation_email

orders_bp = Blueprint('orders', __name__)
logger = logging.getLogger(__name__)


def _request_error_context() -> str:
    request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
    return (
        f"request_id={request_id} method={request.method} path={request.path} "
        f"remote_addr={request.remote_addr}"
    )


def _safe_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _extract_primary_image_url(value):
    if not value:
        return None

    if isinstance(value, list):
        return next((str(item).strip() for item in value if str(item).strip()), None)

    raw = str(value).strip()
    if not raw:
        return None

    if raw.startswith('['):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return next((str(item).strip() for item in parsed if str(item).strip()), None)
        except Exception:
            return raw[:255]

    return raw[:255]


def _column_type_name(table_name: str, column_name: str) -> str:
    try:
        inspector = inspect(db.engine)
        for column in inspector.get_columns(table_name):
            if column.get('name') == column_name:
                return str(column.get('type')).lower()
    except Exception:
        logger.warning('Could not inspect schema for %s.%s', table_name, column_name, exc_info=True)
    return ''


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

    # Some legacy deployments have shipping_info/customizations as TEXT rather than JSON.
    # Detect and serialize values to avoid JSON type cast failures at INSERT time.
    shipping_info_db_value = shipping_info
    shipping_col_type = _column_type_name('orders', 'shipping_info')
    if shipping_col_type and 'json' not in shipping_col_type:
        shipping_info_db_value = json.dumps(shipping_info)

    customizations_col_type = _column_type_name('order_items', 'customizations')

    try:
        order = Order(
            user_id=current_user_id(),
            total_price=float(data.get('total_price', 0) or 0),
            # Keep universal status for maximum DB compatibility; quote intent stays in payment_method.
            status='pending',
            shipping_info=shipping_info_db_value,
        )
        db.session.add(order)
        db.session.flush()

        for idx, item in enumerate(items_data, start=1):
            if not isinstance(item, dict):
                db.session.rollback()
                return jsonify({'message': f'Invalid order item at position {idx}'}), 400

            product_id = _safe_uuid(item.get('product_id'))
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

            customizations_value = item.get('customizations') if isinstance(item, dict) else None
            if customizations_col_type and 'json' not in customizations_col_type and customizations_value is not None:
                customizations_value = json.dumps(customizations_value)

            oi = OrderItem(
                order_id=order.id,
                product_id=product_id,
                quantity=quantity,
                unit_price=product.price,
                unit_cost=product.cost_price if product.cost_price is not None else 0,
                product_title=product.title,
                product_image=_extract_primary_image_url(product.image_url),
                customizations=customizations_value,
            )
            db.session.add(oi)

        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.exception('Order creation failed via ORM, attempting SQL fallback | %s', _request_error_context())

        try:
            user_id_value = str(current_user_id()) if current_user_id() is not None else None
            if user_id_value is None:
                return jsonify({'message': 'Authentication error. Please sign in again.'}), 401

            # Minimal, schema-tolerant order insert
            fallback_order_id = db.session.execute(
                text(
                    """
                    INSERT INTO orders (user_id, total_price, status, created_at)
                    VALUES (:uid, :tp, :status, NOW())
                    RETURNING id
                    """
                ),
                {
                    'uid': user_id_value,
                    'tp': float(data.get('total_price', 0) or 0),
                    'status': 'pending',
                },
            ).scalar()

            if fallback_order_id is None:
                raise RuntimeError('SQL fallback did not return an order id')

            for idx, item in enumerate(items_data, start=1):
                if not isinstance(item, dict):
                    continue

                product_id = _safe_uuid(item.get('product_id'))
                quantity = item.get('quantity')
                if product_id is None or quantity is None:
                    continue

                quantity = int(quantity)
                if quantity <= 0:
                    continue

                product = Product.query.get(product_id)
                if not product:
                    continue

                if not is_quote_request and product.stock is not None:
                    product.stock = max(int(product.stock) - quantity, 0)

                db.session.execute(
                    text(
                        """
                        INSERT INTO order_items (order_id, product_id, quantity, unit_price, unit_cost, product_title, product_image)
                        VALUES (:oid, :pid, :qty, :unit_price, :unit_cost, :title, :image)
                        """
                    ),
                    {
                        'oid': int(fallback_order_id),
                        'pid': str(product_id),
                        'qty': int(quantity),
                        'unit_price': float(product.price or 0),
                        'unit_cost': float(product.cost_price or 0),
                        'title': product.title,
                        'image': _extract_primary_image_url(product.image_url),
                    },
                )

            db.session.commit()

            created_row = db.session.execute(
                text(
                    """
                    SELECT id, user_id, total_price, status, created_at
                    FROM orders
                    WHERE id = :oid
                    """
                ),
                {'oid': int(fallback_order_id)},
            ).mappings().first()

            response_payload = {
                'id': int(fallback_order_id),
                'user_id': str(created_row.get('user_id')) if created_row else user_id_value,
                'total_price': float(created_row.get('total_price') or 0) if created_row else float(data.get('total_price', 0) or 0),
                'status': (created_row.get('status') if created_row else 'pending') or 'pending',
                'shipping_info': shipping_info,
                'created_at': created_row.get('created_at').isoformat() if created_row and created_row.get('created_at') else None,
                'items': [],
                'fallback_mode': True,
            }
            return jsonify(response_payload), 201
        except Exception:
            db.session.rollback()
            logger.exception('Order creation failed in SQL fallback as well | %s', _request_error_context())
            return jsonify({'message': 'Failed to create order. Please try again.'}), 500

    user_account = order.user or db.session.get(User, order.user_id)
    customer_email = (
        shipping_info.get('email')
        or (user_account.email if user_account else '')
        or ''
    ).strip()
    customer_name = ' '.join([
        str(shipping_info.get('first_name') or '').strip(),
        str(shipping_info.get('last_name') or '').strip(),
    ]).strip() or (user_account.name if user_account else 'there')

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
    try:
        if current_user_role() == 'admin':
            orders_rows = db.session.execute(
                text(
                    """
                    SELECT id, user_id, total_price, status, shipping_info, created_at
                    FROM orders
                    ORDER BY created_at DESC
                    """
                )
            ).mappings().all()
        else:
            orders_rows = db.session.execute(
                text(
                    """
                    SELECT id, user_id, total_price, status, shipping_info, created_at
                    FROM orders
                    WHERE CAST(user_id AS TEXT) = :uid
                    ORDER BY created_at DESC
                    """
                ),
                {'uid': str(current_user_id())},
            ).mappings().all()

        payload = []
        for row in orders_rows:
            item_rows = db.session.execute(
                text(
                    """
                    SELECT id, product_id, quantity, unit_price, unit_cost, product_title, product_image, customizations
                    FROM order_items
                    WHERE order_id = :oid
                    ORDER BY id ASC
                    """
                ),
                {'oid': row['id']},
            ).mappings().all()

            created_at = row.get('created_at')
            created_at_value = None
            if created_at is not None:
                created_at_value = created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at)

            payload.append({
                'id': row['id'],
                'user_id': str(row.get('user_id')) if row.get('user_id') is not None else None,
                'user': None,
                'total_price': float(row.get('total_price') or 0),
                'status': row.get('status'),
                'shipping_info': row.get('shipping_info') if isinstance(row.get('shipping_info'), dict) else (row.get('shipping_info') or {}),
                'created_at': created_at_value,
                'items': [
                    {
                        'id': item['id'],
                        'product_id': str(item.get('product_id')) if item.get('product_id') is not None else None,
                        'quantity': item.get('quantity'),
                        'unit_price': float(item.get('unit_price')) if item.get('unit_price') is not None else None,
                        'unit_cost': float(item.get('unit_cost')) if item.get('unit_cost') is not None else None,
                        'product_title': item.get('product_title'),
                        'product_image': item.get('product_image'),
                        'customizations': item.get('customizations'),
                        'product': None,
                    }
                    for item in item_rows
                ],
            })

        return jsonify(payload), 200
    except Exception:
        db.session.rollback()
        logger.exception('Failed to list orders; returning empty list | %s', _request_error_context())
        return jsonify([]), 200


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
