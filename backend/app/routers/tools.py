from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from .. import tool_service as svc
from ..db import get_db
from ..deps import current_user
from ..models import User
from ..ratelimit import rate_limit
from ..schemas import ConnectIn, ConnectionOut, ToolOut

router = APIRouter(prefix="/api/tools")


def _ip(r: Request) -> str:
    return r.client.host if r.client else ""


@router.get("", response_model=list[ToolOut])
def list_tools(capability: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.list_tools(db, user, capability)


@router.get("/connections", response_model=list[ConnectionOut])
def list_connections(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.connections(db, user)


@router.post("/connect", response_model=ConnectionOut, dependencies=[Depends(rate_limit("connect", 10))])
def connect(body: ConnectIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = svc.connect(db, user, body.provider, body.api_key.get_secret_value(), _ip(request))
    return {"provider": r.provider, "key_hint": r.key_hint, "connected_at": r.created_at}


@router.delete("/connect/{provider}", status_code=204)
def disconnect(provider: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    svc.disconnect(db, user, provider, _ip(request))


@router.get("/{tool_id}", response_model=ToolOut)
def get_tool(tool_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.get_tool(db, user, tool_id)
