import os
from pathlib import Path
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from sqlalchemy import inspect, text
from werkzeug.exceptions import HTTPException

from config.config import Config
from models.models import db
from routes.auth import auth_bp
from routes.products import products_bp
from routes.orders import orders_bp
from routes.users import users_bp
from routes.vendors import vendors_bp
from services.email_service import sendgrid_health_payload
from sockets.chat import register_socket_events

socketio = SocketIO()


def _allowed_origins(app):
    frontend_url = app.config.get('FRONTEND_URL', '').rstrip('/')
    extra_origins = os.getenv('CORS_ALLOWED_ORIGINS', '')
    origins = {
        frontend_url,
        'http://localhost:5173',
        'http://127.0.0.1:5173',
        'https://hok-interior.netlify.app',
    }
    origins.update(origin.strip().rstrip('/') for origin in extra_origins.split(',') if origin.strip())
    return [origin for origin in origins if origin]


def _ensure_order_item_columns(app):
    inspector = inspect(db.engine)
    existing_columns = {column['name'] for column in inspector.get_columns('order_items')}
    alterations = []

    if 'unit_price' not in existing_columns:
        alterations.append('ALTER TABLE order_items ADD COLUMN unit_price NUMERIC(10, 2)')
    if 'product_title' not in existing_columns:
        alterations.append('ALTER TABLE order_items ADD COLUMN product_title VARCHAR(255)')
    if 'product_image' not in existing_columns:
        alterations.append('ALTER TABLE order_items ADD COLUMN product_image TEXT')
    if 'customizations' not in existing_columns:
        alterations.append('ALTER TABLE order_items ADD COLUMN customizations JSON')

    if not alterations:
        return

    with db.engine.begin() as connection:
        for statement in alterations:
            connection.execute(text(statement))
    app.logger.info('Applied lightweight order_items schema updates: %s', ', '.join(alterations))


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    allowed_origins = _allowed_origins(app)

    CORS(app, resources={r'/api/*': {'origins': allowed_origins}}, supports_credentials=True)

    db.init_app(app)
    JWTManager(app)
    socketio.init_app(app, cors_allowed_origins=allowed_origins, async_mode='threading')

    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(products_bp, url_prefix='/api')
    app.register_blueprint(orders_bp, url_prefix='/api')
    app.register_blueprint(users_bp, url_prefix='/api')
    app.register_blueprint(vendors_bp, url_prefix='/api')

    register_socket_events(socketio)

    with app.app_context():
        db.create_all()
        _ensure_order_item_columns(app)

    uploads_root = Path(app.config['UPLOAD_FOLDER'])
    uploads_root.mkdir(parents=True, exist_ok=True)

    @app.get('/uploads/<path:filename>')
    def uploaded_file(filename):
        return send_from_directory(uploads_root, filename)

    @app.get('/api/health/email')
    def email_health():
        payload = sendgrid_health_payload()
        return jsonify(payload), 200

    # ── JSON error handlers (must be inside create_app so they bind to this app) ──
    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        """Return JSON for all HTTP errors (404, 405, etc.) so the
        frontend always receives a parseable response."""
        return jsonify({"message": e.description}), e.code

    @app.errorhandler(Exception)
    def handle_exception(e):
        """Catch-all for unhandled exceptions — return JSON 500 instead
        of the Werkzeug HTML debugger page."""
        app.logger.exception("Unhandled server error: %s", e)
        return jsonify({"message": "An internal server error occurred. Please try again."}), 500

    return app


app = create_app()

if __name__ == '__main__':
    # FLASK_DEBUG=1 enables Werkzeug reloader; keep it off by default so that
    # unhandled exceptions return JSON (not the HTML interactive debugger).
    debug = os.getenv('FLASK_DEBUG', '0') == '1'
    socketio.run(app, debug=debug, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
