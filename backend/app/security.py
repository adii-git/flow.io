import hashlib
import uuid
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from cryptography.fernet import Fernet
from .config import get_settings

_ph = PasswordHasher()
DUMMY_HASH = _ph.hash("not-a-real-password")  # equalises timing when the email is unknown


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_access_token(user_id: uuid.UUID) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.access_ttl_min)
    return jwt.encode({"sub": str(user_id), "exp": exp, "typ": "access"}, s.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> uuid.UUID | None:
    try:
        data = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
        return uuid.UUID(data["sub"]) if data.get("typ") == "access" else None
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


def encrypt_secret(plain: str) -> str:
    return Fernet(get_settings().fernet_key.encode()).encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    return Fernet(get_settings().fernet_key.encode()).decrypt(token.encode()).decode()
