from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity


def create_user_access_token(user):
    normalized_role = (user.role or "customer").strip().lower()
    return create_access_token(
        identity=str(user.id),
        additional_claims={"role": normalized_role},
    )


def current_user_id():
    identity = get_jwt_identity()
    return int(identity) if identity is not None else None


def current_user_role():
    return get_jwt().get("role")


def token_user_id(decoded_token):
    subject = decoded_token.get("sub")
    return int(subject) if subject is not None else None


def token_user_role(decoded_token):
    return decoded_token.get("role")