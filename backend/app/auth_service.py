import secrets
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import get_settings
from .models import User, now
from .repositories import TokenRepo, UserRepo, audit
from .security import (DUMMY_HASH, create_access_token, hash_password, hash_token, verify_password)

BAD_LOGIN = HTTPException(401, "Email or password didn't match. Check both and try again.")
BAD_SESSION = HTTPException(401, "Your session has ended. Sign in again to continue.")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _issue(db: Session, user: User, family_id: uuid.UUID | None = None) -> tuple[str, str]:
    s = get_settings()
    raw = secrets.token_urlsafe(48)
    TokenRepo(db).add(user.id, family_id or uuid.uuid4(), hash_token(raw), now() + timedelta(days=s.refresh_ttl_days))
    return create_access_token(user.id), raw


def register(db: Session, email: str, password: str, name: str, ip: str):
    users = UserRepo(db)
    if users.by_email(email):
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    try:
        user = users.create(email, hash_password(password), name.strip())
        user.is_admin = email.lower() in get_settings().admins
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    access, raw = _issue(db, user)
    audit(db, "auth.register", user.id, ip)
    db.commit()
    return user, access, raw


def login(db: Session, email: str, password: str, ip: str):
    user = UserRepo(db).by_email(email)
    ok = verify_password(password, user.password_hash if user else DUMMY_HASH)
    if not (user and ok and user.is_active):
        audit(db, "auth.login_failed", user.id if user else None, ip)
        db.commit()
        raise BAD_LOGIN
    access, raw = _issue(db, user)
    audit(db, "auth.login", user.id, ip)
    db.commit()
    return user, access, raw


def refresh(db: Session, raw: str | None, ip: str):
    tokens = TokenRepo(db)
    rt = tokens.by_hash(hash_token(raw)) if raw else None
    if not rt:
        raise BAD_SESSION
    if rt.revoked_at:  # a used token came back: assume theft, end the whole session family
        tokens.revoke_family(rt.family_id)
        audit(db, "auth.refresh_reuse", rt.user_id, ip)
        db.commit()
        raise BAD_SESSION
    user = UserRepo(db).by_id(rt.user_id)
    if _aware(rt.expires_at) < now() or not user or not user.is_active:
        raise BAD_SESSION
    rt.revoked_at = now()
    access, new_raw = _issue(db, user, rt.family_id)
    db.commit()
    return user, access, new_raw


def logout(db: Session, raw: str | None, ip: str) -> None:
    rt = TokenRepo(db).by_hash(hash_token(raw)) if raw else None
    if rt:
        TokenRepo(db).revoke_family(rt.family_id)
        audit(db, "auth.logout", rt.user_id, ip)
        db.commit()
