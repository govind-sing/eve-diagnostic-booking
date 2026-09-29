import os

# Must be set before importing anything under app/, since app.config reads
# these at import time. SQLAlchemy's create_engine() is lazy (doesn't
# actually connect until first use), so a dummy DATABASE_URL here is fine;
# each test gets its own real SQLite engine via the db_session fixture below,
# wired in through a dependency override.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def db_session(tmp_path):
    """A fresh SQLite database file per test, so tests never share state."""
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False
    )

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield testing_session_local
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def client(db_session):
    return TestClient(app)


# --- shared helpers used across test modules --------------------------------


def signup(client, email, password="supersecret123", role="patient", full_name=None):
    payload = {"email": email, "password": password, "role": role}
    if full_name:
        payload["full_name"] = full_name
    return client.post("/auth/signup", json=payload)


def login(client, email, password="supersecret123"):
    return client.post("/auth/login", json={"email": email, "password": password})


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_token(client):
    signup(client, "admin@example.com", role="admin")
    resp = login(client, "admin@example.com")
    return resp.json()["access_token"]


@pytest.fixture()
def patient_token(client):
    signup(client, "patient@example.com", role="patient")
    resp = login(client, "patient@example.com")
    return resp.json()["access_token"]


@pytest.fixture()
def other_patient_token(client):
    signup(client, "other@example.com", role="patient")
    resp = login(client, "other@example.com")
    return resp.json()["access_token"]


@pytest.fixture()
def centre_and_test(client, admin_token):
    """Creates one diagnostic centre with one test under it, as admin."""
    centre_resp = client.post(
        "/centres/",
        json={"name": "City Diagnostics", "location": "Indore"},
        headers=auth_headers(admin_token),
    )
    centre_id = centre_resp.json()["id"]

    test_resp = client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "Complete Blood Count", "price": 499.00},
        headers=auth_headers(admin_token),
    )
    test_id = test_resp.json()["id"]

    return {"centre_id": centre_id, "test_id": test_id}
