from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .db import get_db
from .models import User
from .repositories import UserRepo
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                 db: Session = Depends(get_db)) -> User:
    uid = decode_access_token(creds.credentials) if creds else None
    user = UserRepo(db).by_id(uid) if uid else None
    if not user or not user.is_active:
        raise HTTPException(401, "Sign in to continue.")
    return user
