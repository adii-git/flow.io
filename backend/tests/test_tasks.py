import pytest

OBJ = "Build a Python script that cleans a sales CSV and charts monthly revenue"


def signup(c, email):
    r = c.post("/api/auth/register", json={"email": email, "password": "correct-horse-battery", "display_name": "T"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def a(client): return signup(client, "a@example.com")


def test_requires_auth(client):
    assert client.post("/api/tasks", json={"objective": OBJ}).status_code == 401
    assert client.get("/api/tasks").status_code == 401


def test_create_builds_steps_and_context(client, a):
    r = client.post("/api/tasks", json={"objective": OBJ}, headers=a)
    assert r.status_code == 201
    t = r.json()
    caps = [s["capability"] for s in t["subtasks"]]
    assert caps[-1] == "validation" and "code_generation" in caps
    assert [s["position"] for s in t["subtasks"]] == list(range(len(caps)))
    assert t["subtasks"][0]["depends_on"] == [] and t["subtasks"][1]["depends_on"] == [t["subtasks"][0]["id"]]
    assert t["context_count"] == 1 + len(t["plan"]["requirements"]) and t["tools_used"] == [] and t["plan"]["source"] == "heuristic"


def test_validation(client, a):
    assert client.post("/api/tasks", json={"objective": "a"}, headers=a).status_code == 422
    assert client.post("/api/tasks", json={"objective": OBJ, "project_id": "00000000-0000-0000-0000-000000000000"}, headers=a).status_code == 404


def test_isolation_between_users(client, a):
    tid = client.post("/api/tasks", json={"objective": OBJ}, headers=a).json()["id"]
    b = signup(client, "b@example.com")
    assert client.get(f"/api/tasks/{tid}", headers=b).status_code == 404
    assert client.delete(f"/api/tasks/{tid}", headers=b).status_code == 404
    assert client.get("/api/tasks", headers=b).json() == []
    pid = client.post("/api/projects", json={"name": "Mine"}, headers=a).json()["id"]
    assert client.post("/api/tasks", json={"objective": OBJ, "project_id": pid}, headers=b).status_code == 404


def test_projects_filter_list_delete(client, a):
    pid = client.post("/api/projects", json={"name": "Launch"}, headers=a).json()["id"]
    client.post("/api/tasks", json={"objective": OBJ, "project_id": pid}, headers=a)
    t2 = client.post("/api/tasks", json={"objective": "Design a logo for a streetwear brand"}, headers=a).json()["id"]
    assert len(client.get("/api/tasks", headers=a).json()) == 2
    assert len(client.get(f"/api/tasks?project_id={pid}", headers=a).json()) == 1
    assert client.delete(f"/api/tasks/{t2}", headers=a).status_code == 204
    assert client.get(f"/api/tasks/{t2}", headers=a).status_code == 404
    assert client.get("/api/projects", headers=a).json()[0]["name"] == "Launch"
