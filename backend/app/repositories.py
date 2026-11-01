import uuid
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from .models import AuditLog, RefreshToken, Setting, User, now


class UserRepo:
    def __init__(self, db: Session):
        self.db = db

    def by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email.lower()))

    def by_id(self, uid: uuid.UUID) -> User | None:
        return self.db.get(User, uid)

    def create(self, email: str, pw_hash: str, name: str) -> User:
        u = User(email=email.lower(), password_hash=pw_hash, display_name=name)
        self.db.add(u)
        self.db.flush()
        self.db.add(Setting(user_id=u.id))
        return u


class TokenRepo:
    def __init__(self, db: Session):
        self.db = db

    def add(self, user_id, family_id, token_hash, expires_at: datetime) -> RefreshToken:
        t = RefreshToken(user_id=user_id, family_id=family_id, token_hash=token_hash, expires_at=expires_at)
        self.db.add(t)
        return t

    def by_hash(self, h: str) -> RefreshToken | None:
        return self.db.scalar(select(RefreshToken).where(RefreshToken.token_hash == h))

    def revoke_family(self, family_id) -> None:
        self.db.execute(update(RefreshToken)
                        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
                        .values(revoked_at=now()))


def audit(db: Session, action: str, user_id=None, ip: str = "", **meta) -> None:
    db.add(AuditLog(action=action, user_id=user_id, ip=ip, meta=meta))
