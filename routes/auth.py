"""
Authentication routes for HOK Interior Designs.

Endpoints
─────────
POST   /api/register               – create account, send welcome + verify email
POST   /api/login                  – sign in, fire login-alert on new IP
GET    /api/verify-email?token=    – activate account via email link
POST   /api/resend-verification    – request a fresh verification email (JWT required)
POST   /api/forgot-password        – request a password-reset link
POST   /api/reset-password         – apply new password via token
"""

import logging
import secrets
from datetime import datetime, timedelta

import bcrypt
from sqlalchemy import func
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    jwt_required,
)

from auth_utils import create_user_access_token, current_user_id
from models.models import EmailToken, User, db
from services.email_service import (
    send_login_notice,
    send_password_changed,
    send_reset_email,
    send_verify_email,
    send_welcome_email,
)

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _client_ip() -> str:
    """Return real client IP, respecting X-Forwarded-For behind a proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"


def _make_token(user_id: int, token_type: str, hours: int = 24) -> str:
    """
    Generate a cryptographically-safe URL token, persist it, and return the
    raw string.  Caller must call db.session.commit() afterwards.
    Any previous unused tokens of the same type for this user are invalidated.
    """
    # Invalidate old tokens of this type
    EmailToken.query.filter_by(
        user_id=user_id, token_type=token_type, used=False
    ).delete(synchronize_session="fetch")

    raw = secrets.token_urlsafe(32)
    et = EmailToken(
        user_id=user_id,
        token=raw,
        token_type=token_type,
        expires_at=datetime.utcnow() + timedelta(hours=hours),
    )
    db.session.add(et)
    db.session.flush()   # write to DB without full commit so caller can bundle
    return raw


def _validate_password(pw: str):
    """Return an error message string, or None if the password is acceptable."""
    if len(pw) < 8:
        return "Password must be at least 8 characters"
    if not any(c.isdigit() for c in pw):
        return "Password must contain at least one number"
    return None


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _get_user_by_email(email: str):
    normalized = _normalize_email(email)
    if not normalized:
        return None
    return User.query.filter(func.lower(User.email) == normalized).first()


def _configured_admin_email() -> str:
    return _normalize_email(current_app.config.get("ADMIN_EMAIL") or "admin@hokinterior.com")


def _configured_admin_name() -> str:
    return (current_app.config.get("ADMIN_NAME") or "Admin").strip() or "Admin"


def _admin_exists() -> bool:
    return User.query.filter_by(role="admin").first() is not None


# ─── POST /register ───────────────────────────────────────────────────────────

@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    required = ("name", "email", "password")
    if not all(k in data for k in required):
        return jsonify({"message": "Missing fields"}), 400

    name = data["name"].strip()
    email = _normalize_email(data["email"])
    password = data["password"]

    pw_err = _validate_password(password)
    if pw_err:
        return jsonify({"message": pw_err}), 400

    try:
        if _get_user_by_email(email):
            return jsonify({"message": "Email already registered"}), 409

        configured_admin_email = _configured_admin_email()
        wants_admin_account = email == configured_admin_email
        has_admin = _admin_exists()

        if wants_admin_account and has_admin:
            return jsonify({"message": "Admin account already exists. Sign in to continue."}), 409

        role = "admin" if wants_admin_account and not has_admin else "customer"
        email_verified = role == "admin"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        user = User(name=name, email=email, password=hashed, role=role, email_verified=email_verified)
        db.session.add(user)
        db.session.flush()  # populate user.id

        verify_url = None
        if not email_verified:
            verify_token = _make_token(user.id, "verify_email", hours=24)
            frontend_url = current_app.config.get("FRONTEND_URL", "http://localhost:5173")
            verify_url = f"{frontend_url}/verify-email?token={verify_token}"

        db.session.commit()

        if verify_url:
            send_welcome_email(user.email, user.name, verify_url)

        jwt_token = create_user_access_token(user)
        return jsonify({
            "user": user.to_dict(),
            "token": jwt_token,
            "message": (
                f"Admin account created for {configured_admin_email}. You can now access the dashboard."
                if role == "admin"
                else "Account created! Check your email to verify your address."
            ),
        }), 201

    except Exception:
        db.session.rollback()
        logger.exception("Register failed for email=%s", email)
        return jsonify({"message": "Registration failed due to a server error. Please try again."}), 500


# ─── POST /login ──────────────────────────────────────────────────────────────

@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    if not all(k in data for k in ("email", "password")):
        return jsonify({"message": "Missing fields"}), 400

    try:
        user = _get_user_by_email(data["email"])
        if not user or not bcrypt.checkpw(data["password"].encode(), user.password.encode()):
            return jsonify({"message": "Invalid email or password"}), 401

        client_ip = _client_ip()
        prev_ip = user.last_login_ip

        # Persist updated IP
        user.last_login_ip = client_ip
        db.session.commit()

        frontend_url = current_app.config.get("FRONTEND_URL", "http://localhost:5173")
        change_url = f"{frontend_url}/forgot-password"
        time_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        send_login_notice(
            user.email,
            user.name,
            client_ip,
            time_str,
            change_url,
            is_new_location=bool(prev_ip and prev_ip != client_ip),
        )
        logger.info("[auth] Login notice sent to %s", user.email)

        jwt_token = create_user_access_token(user)
        return jsonify({"user": user.to_dict(), "token": jwt_token}), 200

    except Exception:
        db.session.rollback()
        logger.exception("Login failed for email=%s", data.get('email', ''))
        return jsonify({"message": "Login failed due to a server error. Please try again."}), 500


@auth_bp.get("/setup-status")
def setup_status():
    has_admin = _admin_exists()
    return jsonify({
        "has_admin": has_admin,
        "requires_admin_setup": not has_admin,
        "admin_email": _configured_admin_email(),
        "admin_name": _configured_admin_name(),
    }), 200


# ─── GET /verify-email?token= ─────────────────────────────────────────────────

@auth_bp.get("/verify-email")
def verify_email():
    token_str = request.args.get("token", "").strip()
    if not token_str:
        return jsonify({"message": "Token is required"}), 400

    record = EmailToken.query.filter_by(
        token=token_str, token_type="verify_email", used=False
    ).first()

    if not record:
        return jsonify({"message": "Invalid or already-used verification link"}), 400

    if record.expires_at < datetime.utcnow():
        return jsonify({"message": "Verification link has expired. Please request a new one."}), 400

    record.user.email_verified = True
    record.used = True
    db.session.commit()

    return jsonify({"message": "Email verified! You can now enjoy all features.", "user": record.user.to_dict()}), 200


# ─── POST /resend-verification ────────────────────────────────────────────────

@auth_bp.post("/resend-verification")
@jwt_required()
def resend_verification():
    user = db.session.get(User, current_user_id())
    if not user:
        return jsonify({"message": "User not found"}), 404
    if user.email_verified:
        return jsonify({"message": "Email is already verified"}), 400

    verify_token = _make_token(user.id, "verify_email", hours=24)
    db.session.commit()

    frontend_url = current_app.config.get("FRONTEND_URL", "http://localhost:5173")
    send_verify_email(user.email, user.name, f"{frontend_url}/verify-email?token={verify_token}")
    return jsonify({"message": "Verification email sent!"}), 200


# ─── POST /forgot-password ────────────────────────────────────────────────────

@auth_bp.post("/forgot-password")
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = _normalize_email(data.get("email", ""))
    if not email:
        return jsonify({"message": "Email is required"}), 400

    user = _get_user_by_email(email)
    # Always return a generic message to prevent email-enumeration attacks
    if user:
        reset_token = _make_token(user.id, "password_reset", hours=1)
        db.session.commit()

        frontend_url = current_app.config.get("FRONTEND_URL", "http://localhost:5173")
        reset_url = f"{frontend_url}/reset-password?token={reset_token}"
        send_reset_email(user.email, user.name, reset_url)

    return jsonify({"message": "If that email is registered, a reset link has been sent."}), 200


# ─── POST /reset-password ─────────────────────────────────────────────────────

@auth_bp.post("/reset-password")
def reset_password():
    data = request.get_json(silent=True) or {}
    token_str = data.get("token", "").strip()
    new_password = data.get("password", "")

    if not token_str or not new_password:
        return jsonify({"message": "Token and new password are required"}), 400

    pw_err = _validate_password(new_password)
    if pw_err:
        return jsonify({"message": pw_err}), 400

    record = EmailToken.query.filter_by(
        token=token_str, token_type="password_reset", used=False
    ).first()

    if not record:
        return jsonify({"message": "Invalid or already-used reset link"}), 400

    if record.expires_at < datetime.utcnow():
        return jsonify({"message": "Reset link has expired. Please request a new one."}), 400

    user = record.user
    user.password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    record.used = True
    db.session.commit()

    send_password_changed(user.email, user.name)
    return jsonify({"message": "Password reset successfully! You can now sign in."}), 200
