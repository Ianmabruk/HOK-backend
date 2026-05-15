from flask_socketio import SocketIO, emit, join_room
import uuid
from auth_utils import token_user_id, token_user_role
from models.models import db, Chat
from flask_jwt_extended import decode_token

socketio = SocketIO()


def _safe_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def register_socket_events(socketio):

    @socketio.on('connect')
    def on_connect(auth):
        user_id = None
        if auth and auth.get('token'):
            try:
                decoded = decode_token(auth['token'])
                user_id = token_user_id(decoded)
            except Exception:
                pass
        # Admin joins admin room
        if auth and auth.get('token'):
            try:
                decoded = decode_token(auth['token'])
                if token_user_role(decoded) == 'admin':
                    join_room('admin_room')
            except Exception:
                pass

    @socketio.on('user_message')
    def on_user_message(data):
        # Resolve user_id from auth token if available
        user_id = None
        # Extract product context if provided
        product_id = data.get('product_id')
        product_title = data.get('product_title')
        product_price = data.get('product_price')
        product_image = data.get('product_image')

        msg = Chat(
            user_id=user_id,
            sender=data.get('sender', 'Guest'),
            text=data['text'],
            product_id=product_id,
            product_title=product_title,
            product_price=product_price,
            product_image=product_image,
        )
        db.session.add(msg)
        db.session.commit()
        # Notify admin with full product context
        emit('new_user_message', {**msg.to_dict(), 'user_id': user_id}, room='admin_room')
        # Send history back to user
        history = Chat.query.filter_by(user_id=user_id).order_by(Chat.timestamp.asc()).all()
        emit('chat_history', [m.to_dict() for m in history])

    @socketio.on('admin_get_conversations')
    def on_admin_get_conversations():
        from sqlalchemy import func
        # Get latest message per user (by max id)
        subq = db.session.query(
            Chat.user_id,
            func.max(Chat.id).label('max_id')
        ).group_by(Chat.user_id).subquery()

        rows = db.session.query(Chat).join(
            subq, (Chat.user_id == subq.c.user_id) & (Chat.id == subq.c.max_id)
        ).all()

        emit('admin_conversations', [
            {
                'user_id': str(r.user_id) if r.user_id is not None else None,
                'user_name': r.sender,
                'last_message': r.text,
                'product_id': r.product_id,
                'product_title': r.product_title,
                'product_price': r.product_price,
                'product_image': r.product_image,
            }
            for r in rows
        ])

    @socketio.on('admin_get_room')
    def on_admin_get_room(data):
        uid = _safe_uuid(data.get('user_id'))
        msgs = Chat.query.filter_by(user_id=uid).order_by(Chat.timestamp.asc()).all()
        emit('admin_room_messages', [m.to_dict() for m in msgs])

    @socketio.on('admin_reply')
    def on_admin_reply(data):
        uid = _safe_uuid(data.get('user_id'))
        msg = Chat(user_id=uid, sender='Admin', text=data['text'])
        db.session.add(msg)
        db.session.commit()
        emit('chat_message', msg.to_dict(), room=f"user_{str(uid) if uid is not None else ''}")
