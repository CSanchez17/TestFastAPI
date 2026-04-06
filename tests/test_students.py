from datetime import date, timedelta

from fastapi.testclient import TestClient

from .conftest import auth_headers, unique_user_payload


def test_list_available_rooms_public(client: TestClient):
    response = client.get("/rooms")

    assert response.status_code == 200
    rooms = response.json()
    assert isinstance(rooms, list)
    assert len(rooms) >= 1
    assert all(room["is_available"] for room in rooms)


def test_get_room_found(client: TestClient):
    response = client.get("/rooms/1")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert "title" in data


def test_get_room_not_found(client: TestClient):
    response = client.get("/rooms/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Room not found"


def test_create_room_requires_auth(client: TestClient):
    response = client.post(
        "/rooms",
        json={
            "title": "NoAuth Room",
            "description": "Should fail",
            "price_per_night": 100,
            "is_available": True,
        },
    )

    assert response.status_code == 401


def test_host_can_create_update_delete_own_room(client: TestClient):
    headers = auth_headers(client)

    create_response = client.post(
        "/rooms",
        json={
            "title": "Host Room",
            "description": "Nice and clean",
            "price_per_night": 120,
            "is_available": True,
        },
        headers=headers,
    )
    assert create_response.status_code == 200
    room_id = create_response.json()["id"]

    update_response = client.patch(
        f"/rooms/{room_id}",
        json={"price_per_night": 150},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["price_per_night"] == 150

    delete_response = client.delete(f"/rooms/{room_id}", headers=headers)
    assert delete_response.status_code == 204

    get_response = client.get(f"/rooms/{room_id}")
    assert get_response.status_code == 404


def test_guest_cannot_delete_other_host_room(client: TestClient):
    admin_headers = auth_headers(client)

    room_response = client.post(
        "/rooms",
        json={
            "title": "Admin Room",
            "description": "Owned by admin",
            "price_per_night": 110,
            "is_available": True,
        },
        headers=admin_headers,
    )
    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    payload = unique_user_payload()
    register_response = client.post("/auth/register", json=payload)
    assert register_response.status_code == 201

    guest_headers = auth_headers(client, payload["username"], payload["password"])

    forbidden = client.delete(f"/rooms/{room_id}", headers=guest_headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "You can only delete your own rooms"

    client.delete(f"/rooms/{room_id}", headers=admin_headers)


def test_guest_can_book_available_room(client: TestClient):
    payload = unique_user_payload()
    register_response = client.post("/auth/register", json=payload)
    assert register_response.status_code == 201
    guest_headers = auth_headers(client, payload["username"], payload["password"])

    check_in = date.today() + timedelta(days=2)
    check_out = check_in + timedelta(days=2)

    response = client.post(
        "/bookings",
        json={
            "room_id": 1,
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
        },
        headers=guest_headers,
    )

    assert response.status_code == 200
    booking = response.json()
    assert booking["room_id"] == 1
    assert booking["guest_id"] >= 1


def test_guest_cannot_book_own_room(client: TestClient):
    payload = unique_user_payload()
    register_response = client.post("/auth/register", json=payload)
    assert register_response.status_code == 201

    user_headers = auth_headers(client, payload["username"], payload["password"])
    room_response = client.post(
        "/rooms",
        json={
            "title": "My own room",
            "description": "Owner should not book this",
            "price_per_night": 80,
            "is_available": True,
        },
        headers=user_headers,
    )
    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    check_in = date.today() + timedelta(days=5)
    check_out = check_in + timedelta(days=2)

    response = client.post(
        "/bookings",
        json={
            "room_id": room_id,
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
        },
        headers=user_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "You cannot book your own room"


def test_cannot_book_room_when_not_available(client: TestClient):
    admin_headers = auth_headers(client)

    room_response = client.post(
        "/rooms",
        json={
            "title": "Unavailable room",
            "description": "Already occupied",
            "price_per_night": 99,
            "is_available": False,
        },
        headers=admin_headers,
    )
    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    payload = unique_user_payload()
    register_response = client.post("/auth/register", json=payload)
    assert register_response.status_code == 201
    guest_headers = auth_headers(client, payload["username"], payload["password"])

    check_in = date.today() + timedelta(days=7)
    check_out = check_in + timedelta(days=2)

    response = client.post(
        "/bookings",
        json={
            "room_id": room_id,
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
        },
        headers=guest_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Room is not available"
