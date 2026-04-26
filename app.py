import os
import bcrypt
from pathlib import Path
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from werkzeug.exceptions import HTTPException

from config.config import Config
from models.models import db, User
from routes.auth import auth_bp
from routes.products import products_bp
from routes.orders import orders_bp
from routes.users import users_bp
from routes.vendors import vendors_bp
from sockets.chat import register_socket_events

socketio = SocketIO()


def _seed_admin():
    """Create the admin account on first startup if one doesn't exist yet."""
    if User.query.filter_by(role='admin').first():
        return
    admin_email = os.getenv('ADMIN_EMAIL', 'admin@hokinterior.com')
    admin_password = os.getenv('ADMIN_PASSWORD', 'Admin@1234')
    admin_name = os.getenv('ADMIN_NAME', 'Admin')
    hashed = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()
    admin = User(
        name=admin_name,
        email=admin_email,
        password=hashed,
        role='admin',
        email_verified=True,
    )
    db.session.add(admin)
    db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app, resources={r'/api/*': {'origins': '*'}},
         supports_credentials=True)

    db.init_app(app)
    JWTManager(app)
    socketio.init_app(app, cors_allowed_origins='*', async_mode='threading')

    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(products_bp, url_prefix='/api')
    app.register_blueprint(orders_bp, url_prefix='/api')
    app.register_blueprint(users_bp, url_prefix='/api')
    app.register_blueprint(vendors_bp, url_prefix='/api')

    register_socket_events(socketio)

    with app.app_context():
        db.create_all()
        _seed_admin()

    uploads_root = Path(app.config['UPLOAD_FOLDER'])
    uploads_root.mkdir(parents=True, exist_ok=True)

    @app.get('/uploads/<path:filename>')
    def uploaded_file(filename):
        return send_from_directory(uploads_root, filename)

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
