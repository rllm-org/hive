import base64
import hashlib
import os

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    jwt_secret = os.environ.get("JWT_SECRET", "hive-dev-secret-change-me")
    fernet_key = base64.urlsafe_b64encode(hashlib.sha256(jwt_secret.encode()).digest())
    return Fernet(fernet_key)


def encrypt_value(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt_value(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().decrypt(value.encode()).decode()
