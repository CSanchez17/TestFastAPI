from fastapi.testclient import TestClient

from .conftest import auth_headers, unique_user_payload


def test_login_admin_returns_token(client: TestClient):
    response = client.post(
        "/auth/jwt/login",
        data={"username": "admin", "password": "admin123"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_register_user_then_login(client: TestClient):
    payload = unique_user_payload()

    register_response = client.post("/auth/register", json=payload)
    assert register_response.status_code == 201
    assert register_response.json()["email"] == payload["email"]

    login_response = client.post(
        "/auth/jwt/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    assert login_response.status_code == 200


def test_get_all_users_requires_auth(client: TestClient):
    response = client.get("/all-users")

    assert response.status_code == 401


def test_get_all_users_with_auth(client: TestClient):
    response = client.get("/all-users", headers=auth_headers(client))

    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)
    assert any(user["username"] == "admin" for user in users)


def test_login_wrong_password(client: TestClient):
    response = client.post(
        "/auth/jwt/login",
        data={"username": "admin", "password": "wrongpassword"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "LOGIN_BAD_CREDENTIALS"


def test_login_nonexistent_user(client: TestClient):
    response = client.post(
        "/auth/jwt/login",
        data={"username": "nobody@example.com", "password": "whatever"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "LOGIN_BAD_CREDENTIALS"
