"""Phase 4: ship checks that run without Docker."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from app.models import Base

BACKEND = Path(__file__).resolve().parents[1]


def test_migrations_build_every_model_table(tmp_path):
    db = tmp_path / "m.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}"}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    with sqlite3.connect(db) as c:
        tables = {row[0] for row in c.execute("select name from sqlite_master where type='table'")}
    assert set(Base.metadata.tables) <= tables, set(Base.metadata.tables) - tables


def test_registry_seed_is_valid_and_has_an_image_tool():
    from app.registry.loader import load_specs
    specs = load_specs()
    assert any("image_generation" in s.capabilities and s.provider == "gemini" for s in specs)


def test_health_endpoint(client):
    assert client.get("/api/health").json() == {"status": "ok"}
