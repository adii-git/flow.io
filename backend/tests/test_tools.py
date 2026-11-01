import json
import pytest
from sqlalchemy import select
from app import db as dbmod
from app.models import AuditLog, Tool, ToolConnection
from app.registry.loader import ToolSpec, load_specs, sync_registry
from app.security import decrypt_secret
from tests.test_tasks import signup

KEY = "sk-ant-test-1234567890abcd"


@pytest.fixture()
def a(client): return signup(client, "a@example.com")


def test_seed_is_valid_and_sync_is_idempotent(client):
    n = len(load_specs())
    with dbmod.session_scope() as db:
        r = sync_registry(db)
        assert r == {"added": 0, "updated": n, "retired": 0}
        assert len(db.scalars(select(Tool)).all()) == n


def test_removed_tool_is_retired_not_deleted(client, a):
    removed = load_specs()[0].id
    specs = load_specs()[1:]
    with dbmod.session_scope() as db:
        assert sync_registry(db, specs)["retired"] == 1
    ids = [t["id"] for t in client.get("/api/tools", headers=a).json()]
    assert removed not in ids and len(ids) == len(specs)


def test_bad_specs_rejected():
    base = json.loads(open("app/registry/tools.json").read())["tools"][0]
    with pytest.raises(ValueError):
        ToolSpec(**{**base, "capabilities": ["telepathy"]})
    with pytest.raises(ValueError):
        ToolSpec(**{**base, "config": {"api_key": "x"}})
    with pytest.raises(ValueError):
        ToolSpec(**{**base, "surprise": 1})


def test_requires_auth(client):
    assert client.get("/api/tools").status_code == 401
    assert client.post("/api/tools/connect", json={"provider": "anthropic", "api_key": KEY}).status_code == 401


def test_list_status_and_filter(client, a):
    tools = {t["id"]: t for t in client.get("/api/tools", headers=a).json()}
    assert tools["claude-sonnet-5-5"]["status"] == "needs_key" and tools["python-sandbox"]["status"] == "planned"
    assert "adapter" not in tools["brave-search"] and "config" not in tools["brave-search"]
    cap = client.get("/api/tools?capability=web_research", headers=a).json()
    assert {t["id"] for t in cap} == {"brave-search", "gemini-2-5-flash-lite-search"}
    assert client.get("/api/tools/nope", headers=a).status_code == 404


def test_connect_encrypts_and_never_echoes(client, a):
    r = client.post("/api/tools/connect", json={"provider": "anthropic", "api_key": f"  {KEY} "}, headers=a)
    assert r.status_code == 200 and r.json()["key_hint"] == KEY[-4:] and KEY not in r.text
    with dbmod.session_scope() as db:
        row = db.scalar(select(ToolConnection))
        assert KEY not in row.encrypted_key and decrypt_secret(row.encrypted_key) == KEY
        assert all(KEY not in json.dumps(l.meta) for l in db.scalars(select(AuditLog)))
    assert all(t["status"] == "ready" for t in client.get("/api/tools", headers=a).json() if t["provider"] == "anthropic")
    assert KEY not in client.get("/api/tools/connections", headers=a).text


def test_reconnect_replaces_and_disconnect(client, a):
    client.post("/api/tools/connect", json={"provider": "anthropic", "api_key": KEY}, headers=a)
    client.post("/api/tools/connect", json={"provider": "anthropic", "api_key": "sk-ant-other-9999999"}, headers=a)
    c = client.get("/api/tools/connections", headers=a).json()
    assert len(c) == 1 and c[0]["key_hint"] == "9999"
    assert client.delete("/api/tools/connect/anthropic", headers=a).status_code == 204
    assert client.delete("/api/tools/connect/anthropic", headers=a).status_code == 404
    assert client.get("/api/tools/brave-search", headers=a).json()["status"] == "needs_key"


def test_connect_validation(client, a):
    for body in ({"provider": "anthropic", "api_key": "short"}, {"provider": "anthropic", "api_key": "has space inside key"}):
        assert client.post("/api/tools/connect", json=body, headers=a).status_code == 422
    assert client.post("/api/tools/connect", json={"provider": "nope", "api_key": KEY}, headers=a).status_code == 404
    assert client.post("/api/tools/connect", json={"provider": "conduit", "api_key": KEY}, headers=a).status_code == 404


def test_connections_are_per_user(client, a):
    client.post("/api/tools/connect", json={"provider": "anthropic", "api_key": KEY}, headers=a)
    b = signup(client, "b@example.com")
    assert client.get("/api/tools/connections", headers=b).json() == []
    assert client.get("/api/tools/claude-haiku-4-5", headers=b).json()["status"] == "needs_key"
