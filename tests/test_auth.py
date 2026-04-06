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


def test_login_master_returns_token(client: TestClient):
    response = client.post(
        "/auth/jwt/login",
        data={"username": "master", "password": "master"},
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


def test_users_me_is_not_interpreted_as_id(client: TestClient):
    response = client.get("/users/me", headers=auth_headers(client))

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "admin"


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


def test_admin_user_detail_hides_sensitive_and_raw_relationship_fields(client: TestClient):
    response = client.get("/admin/user/details/1")

    assert response.status_code == 200
    html = response.text
    assert "hashed_password" not in html
    assert "&lt;models.Booking object" not in html
    assert "&lt;models.Room object" not in html
    assert "Rooms (count)" in html
    assert "Bookings (count)" in html
    assert "Room References" in html
    assert "Booking References" in html
    assert "/admin/room/details/" in html


def test_admin_can_create_user_with_password_and_login(client: TestClient):
    username = unique_user_payload()["username"]
    password = "supersecret123"

    create_response = client.post(
        "/admin/user/create",
        data={
            "username": username,
            "email": f"{username}@example.com",
            "hashed_password": password,
            "is_host": "y",
            "is_active": "y",
            "is_superuser": "",
            "is_verified": "y",
            "save": "Save",
        },
    )

    assert create_response.status_code in (200, 302)

    login_response = client.post(
        "/auth/jwt/login",
        data={"username": username, "password": password},
    )

    assert login_response.status_code == 200
    assert "access_token" in login_response.json()


def test_admin_create_user_duplicate_username_returns_clear_error(client: TestClient):
    response = client.post(
        "/admin/user/create",
        data={
            "username": "master",
            "email": "master2@example.com",
            "hashed_password": "master",
            "is_host": "",
            "is_active": "y",
            "is_superuser": "",
            "is_verified": "y",
            "save": "Save",
        },
    )

    assert response.status_code == 400
    assert "Username already exists" in response.text
