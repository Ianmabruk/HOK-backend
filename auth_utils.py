from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity
import uuid


def create_user_access_token(user):
    normalized_role = (user.role or "customer").strip().lower()
    return create_access_token(
        identity=str(user.id),
        additional_claims={"role": normalized_role},
    )


def current_user_id():
    identity = get_jwt_identity()
    if identity is None:
        return None
    try:
        return uuid.UUID(str(identity))
    except (ValueError, TypeError):
        return None


def current_user_role():
    return get_jwt().get("role")


def token_user_id(decoded_token):
    subject = decoded_token.get("sub")
    if subject is None:
        return None
    try:
        return uuid.UUID(str(subject))
    except (ValueError, TypeError):
        return None


def token_user_role(decoded_token):
    return decoded_token.get("role")