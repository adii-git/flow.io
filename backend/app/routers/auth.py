from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from .. import auth_service as svc
from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..models import User
from ..ratelimit import rate_limit
from ..schemas import AuthOut, LoginIn, RegisterIn, UserOut

router = APIRouter(prefix="/api")
COOKIE = "conduit_rt"


def _ip(r: Request) -> str:
    return r.client.host if r.client else ""


def _respond(resp: Response, user: User, access: str, raw: str) -> AuthOut:
    s = get_settings()
    resp.set_cookie(COOKIE, raw, httponly=True, secure=s.cookie_secure, samesite="lax",
                    path="/api/auth", max_age=s.refresh_ttl_days * 86400)
    return AuthOut(access_token=access, expires_in=s.access_ttl_min * 60, user=UserOut.model_validate(user))


def _same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in get_settings().origins:
        raise HTTPException(403, "This request came from an origin Conduit doesn't trust.")


@router.post("/auth/register", response_model=AuthOut, status_code=201,
             dependencies=[Depends(rate_limit("register", 5))])
def register(body: RegisterIn, request: Request, resp: Response, db: Session = Depends(get_db)):
    return _respond(resp, *svc.register(db, body.email, body.password, body.display_name, _ip(request)))


@router.post("/auth/login", response_model=AuthOut, dependencies=[Depends(rate_limit("login", 10))])
def login(body: LoginIn, request: Request, resp: Response, db: Session = Depends(get_db)):
    return _respond(resp, *svc.login(db, body.email, body.password, _ip(request)))


@router.post("/auth/refresh", response_model=AuthOut, dependencies=[Depends(rate_limit("refresh", 30))])
def refresh(request: Request, resp: Response, db: Session = Depends(get_db),
            rt: str | None = Cookie(default=None, alias=COOKIE)):
    _same_origin(request)
    return _respond(resp, *svc.refresh(db, rt, _ip(request)))


@router.post("/auth/logout", status_code=204)
def logout(request: Request, resp: Response, db: Session = Depends(get_db),
           rt: str | None = Cookie(default=None, alias=COOKIE)):
    _same_origin(request)
    svc.logout(db, rt, _ip(request))
    resp.delete_cookie(COOKIE, path="/api/auth")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
