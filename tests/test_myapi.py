import pytest
from httpx import AsyncClient
from asgi_lifespan import LifespanManager
from fastapi.testclient import TestClient
from ..app import fastapi_app


@pytest.mark.asyncio
async def test_get_student_found_alice():
    """Test que obtiene el estudiante Alice (ID 1)."""
    async with LifespanManager(fastapi_app):
        async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
            response = await client.get("/student/1")

    assert response.status_code == 200
    data = response.json()
    assert data["student_id"] == 1
    assert data["name"] == "Alice"
    assert data["age"] == 20
    assert data["year"] == "year 12"


def test_get_student_found_alice():
    """Test que obtiene el estudiante Alice (ID 1)."""
    with TestClient(fastapi_app) as client:
        response = client.get("/student/1")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "Alice"
    assert data["age"] == 20
    assert data["year"] == "year 12"


@pytest.mark.asyncio
async def test_get_student_found_bob():
    """Test que obtiene el estudiante Bob (ID 2)."""
    async with LifespanManager(fastapi_app):
        async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
            response = await client.get("/student/2")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 2
    assert data["name"] == "Bob"
    assert data["age"] == 22
    assert data["year"] == "year 15"


def test_get_student_found_bob():
    """Test que obtiene el estudiante Bob (ID 2)."""
    with TestClient(fastapi_app) as client:
        response = client.get("/student/2")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 2
    assert data["name"] == "Bob"
    assert data["age"] == 22
    assert data["year"] == "year 15"


@pytest.mark.asyncio
async def test_get_student_not_found():
    """Test que intenta obtener un estudiante que no existe."""
    async with LifespanManager(fastapi_app):
        async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
            response = await client.get("/student/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Student not found"


def test_get_student_not_found():
    """Test que intenta obtener un estudiante que no existe."""
    with TestClient(fastapi_app) as client:
        response = client.get("/student/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Student not found"


@pytest.mark.asyncio
async def test_get_student_invalid_id():
    """Test que usa un ID inválido (negativo)."""
    async with LifespanManager(fastapi_app):
        async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
            response = await client.get("/student/-1")

    assert response.status_code == 422  # Validación de Path(gt=0)


def test_get_student_invalid_id():
    """Test que usa un ID inválido (negativo)."""
    with TestClient(fastapi_app) as client:
        response = client.get("/student/-1")

    assert response.status_code == 422  # Validación de Path(gt=0)


@pytest.mark.asyncio
async def test_delete_student_success():
    """Test que elimina exitosamente un estudiante existente."""
    async with LifespanManager(fastapi_app):
        async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
            # Primero crear un estudiante para eliminar
            create_response = await client.post("/student", json={
                "name": "Test Student",
                "age": 25,
                "year": "year 13"
            })
            assert create_response.status_code == 200
            student_data = create_response.json()
            student_id = student_data["id"]

            # Ahora eliminarlo
            delete_response = await client.delete(f"/student/{student_id}")
            assert delete_response.status_code == 204

            # Verificar que ya no existe
            get_response = await client.get(f"/student/{student_id}")
            assert get_response.status_code == 404


def test_delete_student_success():
    """Test que elimina exitosamente un estudiante existente."""
    with TestClient(fastapi_app) as client:
        # Primero crear un estudiante para eliminar
        create_response = client.post("/student", json={
            "name": "Test Student",
            "age": 25,
            "year": "year 13"
        })
        assert create_response.status_code == 200
        student_data = create_response.json()
        student_id = student_data["id"]

        # Ahora eliminarlo
        delete_response = client.delete(f"/student/{student_id}")
        assert delete_response.status_code == 204

        # Verificar que ya no existe
        get_response = client.get(f"/student/{student_id}")
        assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_student_not_found():
    """Test que intenta eliminar un estudiante que no existe."""
    async with LifespanManager(fastapi_app):
        async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
            response = await client.delete("/student/9999")

    assert response.status_code == 404
    assert "nicht gefunden" in response.json()["detail"]


def test_delete_student_not_found():
    """Test que intenta eliminar un estudiante que no existe."""
    with TestClient(fastapi_app) as client:
        response = client.delete("/student/9999")

    assert response.status_code == 404
    assert "nicht gefunden" in response.json()["detail"]
