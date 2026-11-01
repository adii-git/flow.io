import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from .. import files_service
from ..db import get_db
from ..deps import current_user
from ..models import File, User
from ..ratelimit import rate_limit

router = APIRouter(prefix="/api/files")


class FileOut(BaseModel):
    id: uuid.UUID
    filename: str
    size_bytes: int


@router.post("", response_model=FileOut, status_code=201, dependencies=[Depends(rate_limit("upload", 20))])
def upload(file: UploadFile, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = files_service.save_upload(db, user, file, request.client.host if request.client else "")
    return FileOut(id=f.id, filename=f.filename, size_bytes=f.size_bytes)


@router.get("/{file_id}", response_model=FileOut)
def get_file(file_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = db.get(File, file_id)
    if not f or f.user_id != user.id:
        raise HTTPException(404, "That file doesn't exist or isn't yours.")
    return FileOut(id=f.id, filename=f.filename, size_bytes=f.size_bytes)
