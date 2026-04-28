from flask import Blueprint, jsonify, request
from models.models import EmailDeliveryLog, User, db
from flask_jwt_extended import jwt_required

from auth_utils import current_user_id, current_user_role
from services.email_service import send_admin_message

users_bp = Blueprint('users', __name__)


def _admin_only():
    if current_user_role() != 'admin':
        return jsonify({'message': 'Admin only'}), 403
    return None


@users_bp.get('/users')
@jwt_required()
def get_users():
    err = _admin_only()
    if err:
        return err
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([u.to_dict() for u in users])


@users_bp.post('/users/email')
@jwt_required()
def email_users():
    err = _admin_only()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    subject = (data.get('subject') or '').strip()
    message = (data.get('message') or '').strip()
    recipient_mode = (data.get('recipient_mode') or 'selected').strip().lower()
    user_ids = data.get('user_ids') or []

    if not subject:
        return jsonify({'message': 'Email subject is required'}), 400
    if not message:
        return jsonify({'message': 'Email message is required'}), 400

    if recipient_mode == 'all':
        recipients = User.query.filter(User.role != 'admin').order_by(User.created_at.desc()).all()
    elif recipient_mode == 'selected':
        normalized_ids = []
        for raw_id in user_ids:
            try:
                normalized_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue
        if not normalized_ids:
            return jsonify({'message': 'Select at least one user to email'}), 400
        recipients = User.query.filter(
            User.role != 'admin',
            User.id.in_(normalized_ids),
        ).order_by(User.created_at.desc()).all()
    else:
        return jsonify({'message': 'Invalid recipient mode'}), 400

    recipients = [user for user in recipients if user.email]
    if not recipients:
        return jsonify({'message': 'No matching users with email addresses were found'}), 404

    delivery_logs = []
    sender_id = current_user_id()
    for user in recipients:
        delivery_log = EmailDeliveryLog(
            recipient_user_id=user.id,
            triggered_by_user_id=sender_id,
            recipient_name=user.name,
            recipient_email=user.email,
            subject=subject,
            message_preview=message[:280],
            status='queued',
            provider='sendgrid',
        )
        db.session.add(delivery_log)
        delivery_logs.append((user, delivery_log))

    db.session.commit()

    for user, delivery_log in delivery_logs:
        send_admin_message(user.email, user.name, subject, message, delivery_log_id=delivery_log.id)

    return jsonify({
        'message': f'Email queued for {len(recipients)} user(s).',
        'queued_count': len(recipients),
        'recipient_mode': recipient_mode,
        'delivery_logs': [delivery_log.to_dict() for _, delivery_log in delivery_logs],
        'recipients': [
            {'id': user.id, 'name': user.name, 'email': user.email}
            for user in recipients
        ],
    }), 200


@users_bp.get('/users/email/logs')
@jwt_required()
def get_email_logs():
    err = _admin_only()
    if err:
        return err

    limit = request.args.get('limit', default=50, type=int) or 50
    limit = max(1, min(limit, 200))
    logs = EmailDeliveryLog.query.order_by(EmailDeliveryLog.created_at.desc()).limit(limit).all()
    return jsonify([log.to_dict() for log in logs])
