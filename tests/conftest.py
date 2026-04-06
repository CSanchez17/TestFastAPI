from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from ..app import fastapi_app


@pytest.fixture
def client():
    with TestClient(fastapi_app) as test_client:
        yield test_client


def auth_headers(client: TestClient, username: str = "admin", password: str = "admin123") -> dict[str, str]:
    response = client.post(
        "/auth/jwt/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def unique_user_payload() -> dict[str, str]:
    unique = uuid4().hex[:8]
    username = f"user_{unique}"
    return {
        "username": username,
        "email": f"{username}@example.com",
        "password": "secret123",
    }
