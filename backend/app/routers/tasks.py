import uuid
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from .. import files_service, task_service as svc
from ..db import get_db
from ..deps import current_user
from ..models import Project, Task, User
from ..ratelimit import rate_limit
from ..schemas import ProjectIn, ProjectOut, TaskDetail, TaskIn, TaskSummary

router = APIRouter(prefix="/api")


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = Project(user_id=user.id, name=body.name.strip())
    db.add(p)
    db.commit()
    return p


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Project).where(Project.user_id == user.id).order_by(Project.created_at)).all()


@router.post("/tasks", response_model=TaskDetail, status_code=201, dependencies=[Depends(rate_limit("task", 30))])
def create_task(body: TaskIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    files = files_service.claim(db, user, body.file_ids)
    t = svc.create_task(db, user, body.objective, body.project_id, request.client.host if request.client else "", files)
    return svc.detail(db, t)


@router.get("/tasks", response_model=list[TaskSummary])
def list_tasks(project_id: uuid.UUID | None = None, limit: int = Query(30, ge=1, le=50), offset: int = Query(0, ge=0),
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Task).where(Task.user_id == user.id)
    if project_id:
        q = q.where(Task.project_id == project_id)
    rows = db.scalars(q.order_by(Task.created_at.desc()).limit(limit).offset(offset)).all()
    return [{"id": t.id, "title": (t.plan or {}).get("title") or t.objective[:70], "status": t.status,
             "project_id": t.project_id, "created_at": t.created_at} for t in rows]


@router.get("/tasks/{task_id}", response_model=TaskDetail)
def get_task(task_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.detail(db, svc.get_owned(db, user, task_id))


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(svc.get_owned(db, user, task_id))
    db.commit()
