from datetime import date, timedelta

from fastapi.testclient import TestClient

from .conftest import auth_headers, unique_user_payload


def activate_host(client: TestClient, headers: dict[str, str]):
    response = client.post("/hosts/me/activate", headers=headers)
    assert response.status_code == 200


def location_payload(address_line: str, city: str = "Berlin", country: str = "Germany", postal_code: str = "10115"):
    return {
        "address_line": address_line,
        "city": city,
        "country": country,
        "postal_code": postal_code,
    }


def test_list_available_rooms_public(client: TestClient):
    response = client.get("/rooms")

    assert response.status_code == 200
    rooms = response.json()
    assert isinstance(rooms, list)
    assert len(rooms) >= 1
    assert all(room["is_available"] for room in rooms)
    assert "location" in rooms[0]


def test_booking_frontend_page_loads(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "Find a room and book in seconds" in html
    assert "TRAVEL MATCH STUDIO" in html
    assert "concierge-chat" in html
    assert "booking-modal" in html
    assert "/web-static/web/app.js" in html


def test_booking_frontend_javascript_asset_is_served(client: TestClient):
    response = client.get("/web-static/web/app.js")

    assert response.status_code == 200
    assert "openBookingModal" in response.text
    assert "/ai/concierge" in response.text


def test_my_bookings_page_loads(client: TestClient):
    response = client.get("/my-bookings")

    assert response.status_code == 200
    html = response.text
    assert "My Bookings" in html
    assert "/web-static/web/my-bookings.js" in html


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
            "location": location_payload("Hidden Street 1"),
            "description": "Should fail",
            "price_per_night": 100,
            "is_available": True,
        },
    )

    assert response.status_code == 401


def test_non_host_cannot_create_room(client: TestClient):
    payload = unique_user_payload()
    assert client.post("/auth/register", json=payload).status_code == 201
    user_headers = auth_headers(client, payload["username"], payload["password"])

    response = client.post(
        "/rooms",
        json={
            "title": "Not host room",
            "location": location_payload("Denied Road 5"),
            "description": "Denied",
            "price_per_night": 77,
            "is_available": True,
        },
        headers=user_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only hosts can create rooms"


def test_host_can_create_update_delete_own_room(client: TestClient):
    headers = auth_headers(client)
    activate_host(client, headers)

    create_response = client.post(
        "/rooms",
        json={
            "title": "Host Room",
            "location": location_payload("Host Avenue 10"),
            "description": "Nice and clean",
            "price_per_night": 120,
            "is_available": True,
        },
        headers=headers,
    )
    assert create_response.status_code == 200
    room_id = create_response.json()["id"]
    assert create_response.json()["location"]["address_line"] == "Host Avenue 10"

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
    activate_host(client, admin_headers)

    room_response = client.post(
        "/rooms",
        json={
            "title": "Admin Room",
            "location": location_payload("Admin Plaza 1"),
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
    assert forbidden.json()["detail"] == "Only hosts can delete rooms"

    client.delete(f"/rooms/{room_id}", headers=admin_headers)


def test_guest_can_book_available_room(client: TestClient):
    admin_headers = auth_headers(client)
    activate_host(client, admin_headers)

    room_response = client.post(
        "/rooms",
        json={
            "title": "Bookable room",
            "location": location_payload("Booking Street 22"),
            "description": "Fresh available room",
            "price_per_night": 135,
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

    check_in = date.today() + timedelta(days=2)
    check_out = check_in + timedelta(days=2)

    response = client.post(
        "/bookings",
        json={
            "room_id": room_id,
            "start_date": check_in.isoformat(),
            "end_date": check_out.isoformat(),
        },
        headers=guest_headers,
    )

    assert response.status_code == 200
    booking = response.json()
    assert booking["room_id"] == room_id
    assert booking["guest_id"] >= 1
    assert booking["status"] == "confirmed"
    assert booking["booked_price_per_night"] > 0


def test_end_user_can_complete_booking_flow(client: TestClient):
    host_headers = auth_headers(client, "master", "master")
    activate_host(client, host_headers)

    room_response = client.post(
        "/rooms",
        json={
            "title": "Quiet Focus Studio",
            "location": location_payload("Cowork Alley 12", city="Madrid", country="Spain", postal_code="28001"),
            "description": "Quiet room with ergonomic desk near city center.",
            "price_per_night": 79,
            "is_available": True,
        },
        headers=host_headers,
    )
    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    guest_payload = unique_user_payload()
    assert client.post("/auth/register", json=guest_payload).status_code == 201
    guest_headers = auth_headers(client, guest_payload["username"], guest_payload["password"])

    rooms_response = client.get("/rooms")
    assert rooms_response.status_code == 200
    available_ids = {room["id"] for room in rooms_response.json()}
    assert room_id in available_ids

    start = date.today()
    end = start + timedelta(days=2)
    booking_response = client.post(
        "/bookings",
        json={"room_id": room_id, "start_date": start.isoformat(), "end_date": end.isoformat()},
        headers=guest_headers,
    )
    assert booking_response.status_code == 200
    booking = booking_response.json()
    assert booking["room_id"] == room_id

    my_bookings = client.get("/bookings/me", headers=guest_headers)
    assert my_bookings.status_code == 200
    assert any(item["id"] == booking["id"] for item in my_bookings.json())


def test_ai_concierge_recommends_room_with_reason(client: TestClient):
    host_headers = auth_headers(client, "master", "master")
    activate_host(client, host_headers)

    room_response = client.post(
        "/rooms",
        json={
            "title": "Work and Quiet Suite",
            "location": location_payload("Center Desk Road 3", city="Berlin", country="Germany", postal_code="10115"),
            "description": "Quiet suite with ergonomic desk and double-glazed windows near center.",
            "price_per_night": 80,
            "is_available": True,
        },
        headers=host_headers,
    )
    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    concierge_response = client.post(
        "/ai/concierge",
        json={
            "query": "Busco una habitacion tranquila para trabajar cerca del centro que no pase de 80 euros en Berlin",
            "max_results": 3,
        },
    )

    assert concierge_response.status_code == 200
    payload = concierge_response.json()
    assert payload["assistant_message"]
    assert "llm_provider_used" not in payload
    assert payload["recommendations"]
    assert any(item["price_per_night"] <= 80 for item in payload["recommendations"])
    assert any(item["city"] == "Berlin" for item in payload["recommendations"])
    assert any("budget" in item["reason"] or "quiet" in item["reason"] for item in payload["recommendations"])


def test_guest_cannot_book_own_room(client: TestClient):
    payload = unique_user_payload()
    register_response = client.post("/auth/register", json=payload)
    assert register_response.status_code == 201

    user_headers = auth_headers(client, payload["username"], payload["password"])
    activate_host(client, user_headers)
    room_response = client.post(
        "/rooms",
        json={
            "title": "My own room",
            "location": location_payload("Owner Block 3"),
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
            "start_date": check_in.isoformat(),
            "end_date": check_out.isoformat(),
        },
        headers=user_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "You cannot book your own room"


def test_cannot_book_room_when_not_available(client: TestClient):
    admin_headers = auth_headers(client)
    activate_host(client, admin_headers)

    room_response = client.post(
        "/rooms",
        json={
            "title": "Unavailable room",
            "location": location_payload("Unavailable Lane 9"),
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
            "start_date": check_in.isoformat(),
            "end_date": check_out.isoformat(),
        },
        headers=guest_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Room is not available"


def test_invalid_booking_dates_rejected(client: TestClient):
    admin_headers = auth_headers(client)
    activate_host(client, admin_headers)

    room_response = client.post(
        "/rooms",
        json={
            "title": "Date validation room",
            "location": location_payload("Calendar Road 11"),
            "description": "Used for invalid date test",
            "price_per_night": 88,
            "is_available": True,
        },
        headers=admin_headers,
    )
    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    payload = unique_user_payload()
    assert client.post("/auth/register", json=payload).status_code == 201
    guest_headers = auth_headers(client, payload["username"], payload["password"])

    start = date.today() + timedelta(days=3)
    end = start

    response = client.post(
        "/bookings",
        json={"room_id": room_id, "start_date": start.isoformat(), "end_date": end.isoformat()},
        headers=guest_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "end_date must be after start_date"


def test_price_change_does_not_affect_existing_booking(client: TestClient):
    host_headers = auth_headers(client)
    activate_host(client, host_headers)

    room_response = client.post(
        "/rooms",
        json={
            "title": "Price lock room",
            "location": location_payload("Price Street 77"),
            "description": "Testing price protection",
            "price_per_night": 100,
            "is_available": True,
        },
        headers=host_headers,
    )
    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    guest_payload = unique_user_payload()
    assert client.post("/auth/register", json=guest_payload).status_code == 201
    guest_headers = auth_headers(client, guest_payload["username"], guest_payload["password"])

    start = date.today() + timedelta(days=10)
    end = start + timedelta(days=2)

    booking_response = client.post(
        "/bookings",
        json={"room_id": room_id, "start_date": start.isoformat(), "end_date": end.isoformat()},
        headers=guest_headers,
    )
    assert booking_response.status_code == 200
    booking = booking_response.json()
    assert booking["booked_price_per_night"] == 100

    update_response = client.patch(
        f"/rooms/{room_id}",
        json={"price_per_night": 250},
        headers=host_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["price_per_night"] == 250

    status_response = client.patch(
        f"/bookings/{booking['id']}/status",
        json={"status": "confirmed"},
        headers=host_headers,
    )
    assert status_response.status_code == 200
    assert status_response.json()["booked_price_per_night"] == 100


def test_host_dashboard_shows_guest_who_booked(client: TestClient):
    host_headers = auth_headers(client)
    activate_host(client, host_headers)

    room_response = client.post(
        "/rooms",
        json={
            "title": "Dashboard room",
            "location": location_payload("Dashboard Circle 4"),
            "description": "For dashboard assertions",
            "price_per_night": 140,
            "is_available": True,
        },
        headers=host_headers,
    )
    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    guest_payload = unique_user_payload()
    assert client.post("/auth/register", json=guest_payload).status_code == 201
    guest_headers = auth_headers(client, guest_payload["username"], guest_payload["password"])

    start = date.today() + timedelta(days=12)
    end = start + timedelta(days=2)
    booking_response = client.post(
        "/bookings",
        json={"room_id": room_id, "start_date": start.isoformat(), "end_date": end.isoformat()},
        headers=guest_headers,
    )
    assert booking_response.status_code == 200

    dashboard_response = client.get("/dashboard/host", headers=host_headers)
    assert dashboard_response.status_code == 200
    dashboard = dashboard_response.json()
    assert dashboard["total_rooms"] >= 1
    assert dashboard["total_bookings"] >= 1
    assert any(item["guest_username"] == guest_payload["username"] for item in dashboard["bookings"])


def test_guest_dashboard_and_bookings_me(client: TestClient):
    host_headers = auth_headers(client)
    activate_host(client, host_headers)

    room_response = client.post(
        "/rooms",
        json={
            "title": "Guest dashboard room",
            "location": location_payload("Guest Harbor 6"),
            "description": "For guest dashboard assertions",
            "price_per_night": 90,
            "is_available": True,
        },
        headers=host_headers,
    )
    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    guest_payload = unique_user_payload()
    assert client.post("/auth/register", json=guest_payload).status_code == 201
    guest_headers = auth_headers(client, guest_payload["username"], guest_payload["password"])

    start = date.today() + timedelta(days=15)
    end = start + timedelta(days=1)
    booking_response = client.post(
        "/bookings",
        json={"room_id": room_id, "start_date": start.isoformat(), "end_date": end.isoformat()},
        headers=guest_headers,
    )
    assert booking_response.status_code == 200

    my_bookings_response = client.get("/bookings/me", headers=guest_headers)
    assert my_bookings_response.status_code == 200
    my_bookings = my_bookings_response.json()
    assert any(item["room_id"] == room_id for item in my_bookings)

    guest_dashboard_response = client.get("/dashboard/guest", headers=guest_headers)
    assert guest_dashboard_response.status_code == 200
    dashboard = guest_dashboard_response.json()
    assert dashboard["total_bookings"] >= 1
    assert dashboard["active_bookings"] >= 1
    assert dashboard["total_spent_confirmed"] >= 90


def test_host_rooms_me_requires_host_role(client: TestClient):
    payload = unique_user_payload()
    assert client.post("/auth/register", json=payload).status_code == 201
    user_headers = auth_headers(client, payload["username"], payload["password"])

    response = client.get("/hosts/rooms/me", headers=user_headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "Only hosts can view owned rooms"


def test_host_rooms_me_lists_owned_rooms(client: TestClient):
    host_headers = auth_headers(client)
    activate_host(client, host_headers)

    room_response = client.post(
        "/rooms",
        json={
            "title": "Owned list room",
            "location": location_payload("Owned Street 99"),
            "description": "For /rooms/me",
            "price_per_night": 70,
            "is_available": True,
        },
        headers=host_headers,
    )
    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    response = client.get("/hosts/rooms/me", headers=host_headers)
    assert response.status_code == 200
    rooms = response.json()
    assert any(room["id"] == room_id for room in rooms)


def test_admin_room_detail_hides_raw_booking_relationships(client: TestClient):
    host_headers = auth_headers(client)
    activate_host(client, host_headers)

    room_response = client.post(
        "/rooms",
        json={
            "title": "Admin room detail",
            "location": location_payload("Detail Avenue 2"),
            "description": "Admin page cleanup",
            "price_per_night": 101,
            "is_available": True,
        },
        headers=host_headers,
    )
    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    response = client.get(f"/admin/room/details/{room_id}")
    assert response.status_code == 200
    html = response.text
    assert "&lt;models.Booking object" not in html
    assert "Owner Reference" in html
    assert "Booking References" in html
    assert "Location" in html
    assert "/admin/location/details/" in html


def test_admin_booking_detail_hides_raw_relationships_and_legacy_fields(client: TestClient):
    host_headers = auth_headers(client)
    activate_host(client, host_headers)

    room_response = client.post(
        "/rooms",
        json={
            "title": "Admin booking detail room",
            "location": location_payload("Booking Detail Street 55"),
            "description": "Admin booking page cleanup",
            "price_per_night": 111,
            "is_available": True,
        },
        headers=host_headers,
    )
    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    guest_payload = unique_user_payload()
    assert client.post("/auth/register", json=guest_payload).status_code == 201
    guest_headers = auth_headers(client, guest_payload["username"], guest_payload["password"])

    start = date.today() + timedelta(days=20)
    end = start + timedelta(days=2)
    booking_response = client.post(
        "/bookings",
        json={"room_id": room_id, "start_date": start.isoformat(), "end_date": end.isoformat()},
        headers=guest_headers,
    )
    assert booking_response.status_code == 200
    booking_id = booking_response.json()["id"]

    response = client.get(f"/admin/booking/details/{booking_id}")
    assert response.status_code == 200
    html = response.text
    assert "&lt;models.User object" not in html
    assert "&lt;models.Room object" not in html
    assert "check_in" not in html
    assert "check_out" not in html
    assert "Total Price" in html
    assert "Room Reference" in html
    assert "Guest Reference" in html
    assert "/admin/room/details/" in html
    assert "/admin/user/details/" in html


def test_admin_location_edit_uses_country_dependent_city_dropdown(client: TestClient):
    response = client.get("/admin/location/edit/1")

    assert response.status_code == 200
    html = response.text
    assert 'name="city"' in html
    assert 'name="country"' in html
    assert "<select" in html
    assert "countryCityMap" in html
    assert "Berlin" in html
    assert "Germany" in html


def test_admin_location_create_rejects_invalid_country_city_pair(client: TestClient):
    response = client.post(
        "/admin/location/create",
        data={
            "address_line": "Validation Street 3",
            "country": "France",
            "city": "Berlin",
            "postal_code": "75001",
            "save": "Save",
        },
    )

    assert response.status_code == 400
    assert "Selected city does not belong to the selected country" in response.text
