from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import get_settings
from .db import session_scope
from .registry.loader import sync_registry
from sqlalchemy import update
from .models import User
from .routers import admin, auth, execution, files, tasks, tools


@asynccontextmanager
async def lifespan(_):
    with session_scope() as db:  # a broken seed fails startup loudly rather than misrouting later
        sync_registry(db)
        if get_settings().admins:
            db.execute(update(User).where(User.email.in_(get_settings().admins)).values(is_admin=True))
            db.commit()
    yield


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan, title="Conduit API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=get_settings().origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type"])
    app.include_router(auth.router)
    app.include_router(tasks.router)
    app.include_router(tools.router)
    app.include_router(execution.router)
    app.include_router(files.router)
    app.include_router(admin.router)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
