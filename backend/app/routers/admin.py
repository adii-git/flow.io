from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import observability
from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..models import User

router = APIRouter(prefix="/api")


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "This page is for Conduit admins.")
    return user


@router.get("/config")
def config():
    s = get_settings()
    return {"execution_mode": s.execution_mode, "max_upload_bytes": s.max_upload_bytes}


@router.get("/usage")
def usage(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return observability.user_usage(db, user)


@router.get("/admin/metrics")
def metrics(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return observability.admin_metrics(db)
