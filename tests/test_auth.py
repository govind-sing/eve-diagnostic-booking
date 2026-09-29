from tests.conftest import login, signup


def test_signup_defaults_to_patient_role(client):
    resp = signup(client, "alice@example.com")
    assert resp.status_code == 201
    assert resp.json()["role"] == "patient"


def test_signup_with_admin_role(client):
    resp = signup(client, "boss@example.com", role="admin")
    assert resp.status_code == 201
    assert resp.json()["role"] == "admin"


def test_signup_response_never_includes_password_fields(client):
    resp = signup(client, "carol@example.com")
    body = resp.json()
    assert "password" not in body
    assert "hashed_password" not in body


def test_duplicate_signup_rejected(client):
    signup(client, "dave@example.com")
    resp = signup(client, "dave@example.com")
    assert resp.status_code == 409


def test_signup_short_password_rejected(client):
    resp = client.post(
        "/auth/signup", json={"email": "eve@example.com", "password": "short"}
    )
    assert resp.status_code == 422


def test_signup_invalid_email_rejected(client):
    resp = client.post(
        "/auth/signup",
        json={"email": "not-an-email", "password": "supersecret123"},
    )
    assert resp.status_code == 422


def test_login_success_returns_jwt(client):
    signup(client, "frank@example.com")
    resp = login(client, "frank@example.com")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 0


def test_login_wrong_password_rejected(client):
    signup(client, "grace@example.com")
    resp = login(client, "grace@example.com", password="wrongpassword")
    assert resp.status_code == 401


def test_login_unknown_email_rejected(client):
    resp = login(client, "nobody@example.com")
    assert resp.status_code == 401
