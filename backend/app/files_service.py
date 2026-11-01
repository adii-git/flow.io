"""Safe file handling: text formats only, size-capped, random storage names, owner-scoped."""
import re
import uuid
from pathlib import Path
from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import get_settings
from .models import File, User
from .repositories import audit

ALLOWED = {".txt", ".md", ".csv", ".json"}
EXCERPT_CHARS = 20_000


def _clean_name(name: str) -> str:
    base = Path(name or "file").name
    return re.sub(r"[^A-Za-z0-9._\- ]", "_", base)[:120] or "file"


def save_upload(db: Session, user: User, up: UploadFile, ip: str) -> File:
    s = get_settings()
    name = _clean_name(up.filename or "")
    if Path(name).suffix.lower() not in ALLOWED:
        raise HTTPException(415, f"Conduit reads {', '.join(sorted(ALLOWED))} files for now. Convert this one or paste its text into your objective.")
    raw = up.file.read(s.max_upload_bytes + 1)
    if len(raw) > s.max_upload_bytes:
        raise HTTPException(413, f"That file is over {s.max_upload_bytes // 1_000_000} MB. Trim it or split it.")
    if b"\x00" in raw:
        raise HTTPException(415, "That file looks binary, not text. Export it as text and try again.")
    key = uuid.uuid4().hex
    root = Path(s.upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / key
    path.write_bytes(raw)
    path.chmod(0o600)
    f = File(user_id=user.id, filename=name, content_type="text/plain", size_bytes=len(raw), storage_key=key,
             excerpt=raw.decode("utf-8", errors="replace")[:EXCERPT_CHARS])
    db.add(f)
    audit(db, "file.upload", user.id, ip, size=len(raw))
    db.commit()
    return f


def claim(db: Session, user: User, ids: list[uuid.UUID]) -> list[File]:
    if not ids:
        return []
    rows = db.scalars(select(File).where(File.id.in_(ids), File.user_id == user.id, File.task_id.is_(None))).all()
    if len(rows) != len(set(ids)):
        raise HTTPException(404, "One of the attached files wasn't found or is already used by another task. Attach it again.")
    return list(rows)
