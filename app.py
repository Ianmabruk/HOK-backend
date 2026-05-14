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
from routes.before_after import before_after_bp
from routes.site_settings import site_settings_bp
from routes.portfolio import portfolio_bp
from routes.admin_tools import admin_tools_bp
from routes.virtual_interior_services import virtual_interior_services_bp
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
    if 'unit_cost' not in existing_columns:
        alterations.append('ALTER TABLE order_items ADD COLUMN unit_cost NUMERIC(10, 2)')
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


def _ensure_product_columns(app):
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if 'products' not in tables:
        return
    existing = {c['name'] for c in inspector.get_columns('products')}
    if 'cost_price' not in existing:
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE products ADD COLUMN cost_price NUMERIC(10, 2)'))
        app.logger.info('Added cost_price column to products')


def _ensure_before_after_columns(app):
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if 'before_after_projects' not in tables:
        return
    existing = {c['name'] for c in inspector.get_columns('before_after_projects')}
    if 'is_published' not in existing:
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE before_after_projects ADD COLUMN is_published BOOLEAN NOT NULL DEFAULT TRUE'))
        app.logger.info('Added is_published column to before_after_projects')


def _ensure_user_columns(app):
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if 'users' not in tables:
        return
    existing = {c['name'] for c in inspector.get_columns('users')}
    alterations = []
    if 'last_login_at' not in existing:
        alterations.append('ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP')
    if 'last_login_ip' not in existing:
        alterations.append('ALTER TABLE users ADD COLUMN last_login_ip VARCHAR(45)')
    if not alterations:
        return
    with db.engine.begin() as conn:
        for statement in alterations:
            conn.execute(text(statement))
    app.logger.info('Applied lightweight users schema updates: %s', ', '.join(alterations))


def _ensure_portfolio_columns(app):
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if 'portfolio_projects' not in tables:
        return
    existing = {c['name'] for c in inspector.get_columns('portfolio_projects')}
    alterations = []
    if 'video_url' not in existing:
        alterations.append('ALTER TABLE portfolio_projects ADD COLUMN video_url TEXT')
    if not alterations:
        return
    with db.engine.begin() as conn:
        for statement in alterations:
            conn.execute(text(statement))
    app.logger.info('Applied lightweight portfolio schema updates: %s', ', '.join(alterations))


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['MAX_CONTENT_LENGTH'] = app.config.get('MAX_CONTENT_LENGTH') or 120 * 1024 * 1024

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
    app.register_blueprint(before_after_bp, url_prefix='/api')
    app.register_blueprint(site_settings_bp, url_prefix='/api')
    app.register_blueprint(portfolio_bp, url_prefix='/api')
    app.register_blueprint(admin_tools_bp, url_prefix='/api')
    app.register_blueprint(virtual_interior_services_bp, url_prefix='/api')

    register_socket_events(socketio)

    with app.app_context():
        try:
            db.create_all()
            _ensure_user_columns(app)
            _ensure_portfolio_columns(app)
            _ensure_order_item_columns(app)
            _ensure_product_columns(app)
            _ensure_before_after_columns(app)
        except Exception:
            app.logger.exception('Database initialization (create_all + lightweight schema updates) failed; continuing without schema sync.')

    uploads_root = Path(app.config['UPLOAD_FOLDER'])
    uploads_root.mkdir(parents=True, exist_ok=True)

    @app.get('/uploads/<path:filename>')
    def uploaded_file(filename):
        return send_from_directory(uploads_root, filename)

    @app.get('/api/health/email')
    def email_health():
        payload = sendgrid_health_payload()
        return jsonify(payload), 200

    @app.get('/api/health')
    def app_health():
        db_ok = True
        db_error = None
        try:
            db.session.execute(text('SELECT 1'))
        except Exception as exc:
            db_ok = False
            db_error = str(exc)

        payload = {
            'status': 'ok' if db_ok else 'degraded',
            'environment': app.config.get('APP_ENV', 'development'),
            'checks': {
                'database': {
                    'ok': db_ok,
                    'driver': app.config.get('SQLALCHEMY_DATABASE_URI', '').split(':', 1)[0],
                    'error': db_error,
                },
            },
        }
        return jsonify(payload), (200 if payload['status'] == 'ok' else 503)

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
    port = int(os.getenv('PORT', '5000'))
    socketio.run(app, debug=debug, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
