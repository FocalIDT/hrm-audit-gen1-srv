import uuid
import jwt


def decode_jwt(token):
    return jwt.decode(remove_bearer(token), options={"verify_signature": False})


def remove_bearer(token):
    if token.startswith("Bearer "):
        return token[7:]
    return token


def generate_cache_key(*args):
    return ':'.join(str(arg).lower() for arg in args if arg is not None)


def generate_uuid():
    return str(uuid.uuid4())
