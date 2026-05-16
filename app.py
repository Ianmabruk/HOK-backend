import os
import uuid
from flask import Flask, jsonify, request
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
from routes.media import media_bp
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
        'https://localhost:5173',
        'https://127.0.0.1:5173',
        'https://hok-interior.netlify.app',
        'https://hokinterior.com',
        'https://www.hokinterior.com',
        'https://hok-interior.vercel.app',
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


def _ensure_orders_columns(app):
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if 'orders' not in tables:
        return

    existing_columns = {column['name'] for column in inspector.get_columns('orders')}
    alterations = []

    if 'total_price' not in existing_columns:
        alterations.append('ALTER TABLE orders ADD COLUMN total_price NUMERIC(10, 2) NOT NULL DEFAULT 0')
    if 'status' not in existing_columns:
        alterations.append("ALTER TABLE orders ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'pending'")
    if 'shipping_info' not in existing_columns:
        alterations.append('ALTER TABLE orders ADD COLUMN shipping_info JSON')
    if 'created_at' not in existing_columns:
        alterations.append('ALTER TABLE orders ADD COLUMN created_at TIMESTAMP')

    if not alterations:
        return

    with db.engine.begin() as connection:
        for statement in alterations:
            connection.execute(text(statement))
    app.logger.info('Applied lightweight orders schema updates: %s', ', '.join(alterations))


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


def _ensure_vendor_columns(app):
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if 'vendors' not in tables:
        return
    existing = {c['name'] for c in inspector.get_columns('vendors')}
    alterations = []
    if 'contact' not in existing:
        alterations.append('ALTER TABLE vendors ADD COLUMN contact VARCHAR(50)')
    if 'email' not in existing:
        alterations.append('ALTER TABLE vendors ADD COLUMN email VARCHAR(255)')
    if 'address' not in existing:
        alterations.append('ALTER TABLE vendors ADD COLUMN address TEXT')

    if not alterations:
        return

    with db.engine.begin() as conn:
        for statement in alterations:
            conn.execute(text(statement))
    app.logger.info('Applied lightweight vendors schema updates: %s', ', '.join(alterations))


def _ensure_before_after_columns(app):
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if 'before_after_projects' not in tables:
        return
    existing = {c['name'] for c in inspector.get_columns('before_after_projects')}
    alterations = []
    if 'description' not in existing:
        alterations.append('ALTER TABLE before_after_projects ADD COLUMN description TEXT')
    if 'room_type' not in existing:
        alterations.append('ALTER TABLE before_after_projects ADD COLUMN room_type VARCHAR(80)')
    if 'style' not in existing:
        alterations.append('ALTER TABLE before_after_projects ADD COLUMN style VARCHAR(80)')
    if 'before_video_url' not in existing:
        alterations.append('ALTER TABLE before_after_projects ADD COLUMN before_video_url TEXT')
    if 'after_video_url' not in existing:
        alterations.append('ALTER TABLE before_after_projects ADD COLUMN after_video_url TEXT')
    if 'before_poster_url' not in existing:
        alterations.append('ALTER TABLE before_after_projects ADD COLUMN before_poster_url TEXT')
    if 'after_poster_url' not in existing:
        alterations.append('ALTER TABLE before_after_projects ADD COLUMN after_poster_url TEXT')
    if 'sort_order' not in existing:
        alterations.append('ALTER TABLE before_after_projects ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0')
    if 'is_published' not in existing:
        alterations.append('ALTER TABLE before_after_projects ADD COLUMN is_published BOOLEAN NOT NULL DEFAULT TRUE')

    if not alterations:
        return

    with db.engine.begin() as conn:
        for statement in alterations:
            conn.execute(text(statement))
    app.logger.info('Applied lightweight before_after schema updates: %s', ', '.join(alterations))


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
    if 'summary' not in existing:
        alterations.append('ALTER TABLE portfolio_projects ADD COLUMN summary VARCHAR(400)')
    if 'description' not in existing:
        alterations.append('ALTER TABLE portfolio_projects ADD COLUMN description TEXT')
    if 'image_url' not in existing:
        alterations.append('ALTER TABLE portfolio_projects ADD COLUMN image_url TEXT')
    if 'video_url' not in existing:
        alterations.append('ALTER TABLE portfolio_projects ADD COLUMN video_url TEXT')
    if 'room_type' not in existing:
        alterations.append('ALTER TABLE portfolio_projects ADD COLUMN room_type VARCHAR(80)')
    if 'style' not in existing:
        alterations.append('ALTER TABLE portfolio_projects ADD COLUMN style VARCHAR(80)')
    if 'year' not in existing:
        alterations.append('ALTER TABLE portfolio_projects ADD COLUMN year VARCHAR(10)')
    if 'location' not in existing:
        alterations.append('ALTER TABLE portfolio_projects ADD COLUMN location VARCHAR(120)')
    if 'sort_order' not in existing:
        alterations.append('ALTER TABLE portfolio_projects ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0')
    if 'is_published' not in existing:
        alterations.append('ALTER TABLE portfolio_projects ADD COLUMN is_published BOOLEAN NOT NULL DEFAULT TRUE')
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
    app.register_blueprint(media_bp, url_prefix='/api')
    app.register_blueprint(admin_tools_bp, url_prefix='/api')
    app.register_blueprint(virtual_interior_services_bp, url_prefix='/api')

    register_socket_events(socketio)

    with app.app_context():
        try:
            db.create_all()
            _ensure_user_columns(app)
            _ensure_portfolio_columns(app)
            _ensure_orders_columns(app)
            _ensure_order_item_columns(app)
            _ensure_product_columns(app)
            _ensure_vendor_columns(app)
            _ensure_before_after_columns(app)
        except Exception:
            app.logger.exception('Database initialization (create_all + lightweight schema updates) failed; continuing without schema sync.')

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
        error_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
        app.logger.exception(
            "Unhandled server error id=%s method=%s path=%s remote_addr=%s error=%s",
            error_id,
            request.method,
            request.path,
            request.remote_addr,
            e,
        )
        return jsonify({
            "message": "An internal server error occurred. Please try again.",
            "error_id": error_id,
        }), 500

    return app


app = create_app()

if __name__ == '__main__':
    # FLASK_DEBUG=1 enables Werkzeug reloader; keep it off by default so that
    # unhandled exceptions return JSON (not the HTML interactive debugger).
    debug = os.getenv('FLASK_DEBUG', '0') == '1'
    port = int(os.getenv('PORT', '5000'))
    socketio.run(app, debug=debug, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
