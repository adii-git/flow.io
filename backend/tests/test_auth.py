from app.security import decrypt_secret, encrypt_secret

U = {"email": "Ada@Example.com", "password": "correct-horse-battery", "display_name": "Ada"}


def reg(c, **kw):
    return c.post("/api/auth/register", json={**U, **kw})


def test_register_login_me(client):
    r = reg(client)
    assert r.status_code == 201 and r.json()["user"]["email"] == "ada@example.com"
    assert "httponly" in r.headers["set-cookie"].lower()
    tok = client.post("/api/auth/login", json={"email": "ada@example.com", "password": U["password"]}).json()["access_token"]
    me = client.get("/api/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200 and me.json()["display_name"] == "Ada"


def test_duplicate_and_weak_password(client):
    assert reg(client).status_code == 201
    assert reg(client, email="ada@example.com").status_code == 409
    assert reg(client, email="b@example.com", password="short").status_code == 422


def test_wrong_password_is_generic(client):
    reg(client)
    a = client.post("/api/auth/login", json={"email": "ada@example.com", "password": "nope-nope-nope"})
    b = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "nope-nope-nope"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_me_requires_token(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_refresh_rotates_and_reuse_kills_family(client):
    reg(client)
    old = client.cookies.get("conduit_rt")
    assert client.post("/api/auth/refresh").status_code == 200
    new = client.cookies.get("conduit_rt")
    assert new != old
    client.cookies.set("conduit_rt", old, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401  # reuse detected
    client.cookies.set("conduit_rt", new, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401  # family revoked


def test_logout_revokes(client):
    reg(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.post("/api/auth/refresh").status_code == 401


def test_foreign_origin_blocked_on_refresh(client):
    reg(client)
    assert client.post("/api/auth/refresh", headers={"Origin": "https://evil.example"}).status_code == 403


def test_login_rate_limit(client):
    for _ in range(10):
        client.post("/api/auth/login", json={"email": "x@example.com", "password": "whatever-long"})
    assert client.post("/api/auth/login", json={"email": "x@example.com", "password": "whatever-long"}).status_code == 429


def test_secret_roundtrip_is_not_plaintext():
    t = encrypt_secret("sk-test-123")
    assert "sk-test" not in t and decrypt_secret(t) == "sk-test-123"
