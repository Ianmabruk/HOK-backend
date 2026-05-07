import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import text

from auth_utils import current_user_role
from models.models import Order, OrderItem, db

admin_tools_bp = Blueprint('admin_tools', __name__)
logger = logging.getLogger(__name__)


@admin_tools_bp.post('/admin/reset-sales-data')
@jwt_required()
def reset_sales_data():
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403

    payload = request.get_json(silent=True) or {}
    if payload.get('confirm') != 'RESET':
        return jsonify({'message': 'Confirmation required. Send {"confirm":"RESET"}'}), 400

    try:
        deleted_orders = Order.query.count()
        deleted_items = OrderItem.query.count()

        engine_name = db.session.bind.dialect.name if db.session.bind is not None else ''

        if engine_name == 'postgresql':
            # Fast and reliable on Postgres; also resets identity values.
            db.session.execute(text('TRUNCATE TABLE order_items, orders RESTART IDENTITY CASCADE'))
        else:
            OrderItem.query.delete(synchronize_session=False)
            Order.query.delete(synchronize_session=False)

            # Best-effort sequence reset for SQLite only.
            if engine_name == 'sqlite':
                has_sqlite_sequence = db.session.execute(
                    text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence' LIMIT 1")
                ).scalar()
                if has_sqlite_sequence:
                    db.session.execute(text("DELETE FROM sqlite_sequence WHERE name IN ('orders', 'order_items')"))

        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('Failed to reset sales data')
        return jsonify({'message': 'Failed to reset sales data. Please try again.'}), 500

    return jsonify({
        'message': 'Sales and order history reset successfully.',
        'deleted': {
            'orders': deleted_orders,
            'order_items': deleted_items,
        },
        'totals': {
            'sales': 0,
            'cogs': 0,
            'orders': 0,
        },
    }), 200
