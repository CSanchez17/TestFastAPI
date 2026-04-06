from fastapi.testclient import TestClient

from .conftest import auth_headers


def test_get_student_found(client: TestClient):
    response = client.get("/student/1")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "Alice"


def test_get_student_not_found(client: TestClient):
    response = client.get("/student/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Student not found"


def test_get_student_invalid_id(client: TestClient):
    response = client.get("/student/-1")

    assert response.status_code == 422


def test_create_student_requires_auth(client: TestClient):
    response = client.post(
        "/student",
        json={"name": "NoAuth", "age": 18, "year": "year 10"},
    )

    assert response.status_code == 401


def test_create_and_delete_student_success(client: TestClient):
    headers = auth_headers(client)

    create_response = client.post(
        "/student",
        json={"name": "Test Student", "age": 25, "year": "year 13"},
        headers=headers,
    )
    assert create_response.status_code == 200
    student_id = create_response.json()["id"]

    delete_response = client.delete(f"/student/{student_id}", headers=headers)
    assert delete_response.status_code == 204

    get_response = client.get(f"/student/{student_id}")
    assert get_response.status_code == 404


def test_delete_student_not_found_returns_404(client: TestClient):
    response = client.delete("/student/999999", headers=auth_headers(client))

    assert response.status_code == 404
    assert response.json()["detail"] == "Student not found"
