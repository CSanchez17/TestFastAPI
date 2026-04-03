import pytest
from httpx import AsyncClient
from asgi_lifespan import LifespanManager
from fastapi.testclient import TestClient
from ..myapi import app


@pytest.mark.asyncio
async def test_get_student_found_alice():
    """Test que obtiene el estudiante Alice (ID 1)."""
    async with LifespanManager(app):
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/students/1")

    assert response.status_code == 200
    data = response.json()
    assert data["student_id"] == 1
    assert data["name"] == "Alice"
    assert data["age"] == 20
    assert data["year"] == "year 12"


def test_get_student_found_alice():
    """Test que obtiene el estudiante Alice (ID 1)."""
    with TestClient(app) as client:
        response = client.get("/students/1")

    assert response.status_code == 200
    data = response.json()
    assert data["student_id"] == 1
    assert data["name"] == "Alice"
    assert data["age"] == 20
    assert data["year"] == "year 12"


@pytest.mark.asyncio
async def test_get_student_found_bob():
    """Test que obtiene el estudiante Bob (ID 2)."""
    async with LifespanManager(app):
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/students/2")

    assert response.status_code == 200
    data = response.json()
    assert data["student_id"] == 2
    assert data["name"] == "Bob"
    assert data["age"] == 22
    assert data["year"] == "year 15"


def test_get_student_found_bob():
    """Test que obtiene el estudiante Bob (ID 2)."""
    with TestClient(app) as client:
        response = client.get("/students/2")

    assert response.status_code == 200
    data = response.json()
    assert data["student_id"] == 2
    assert data["name"] == "Bob"
    assert data["age"] == 22
    assert data["year"] == "year 15"


@pytest.mark.asyncio
async def test_get_student_not_found():
    """Test que intenta obtener un estudiante que no existe."""
    async with LifespanManager(app):
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/students/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Student not found"


def test_get_student_not_found():
    """Test que intenta obtener un estudiante que no existe."""
    with TestClient(app) as client:
        response = client.get("/students/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Student not found"


@pytest.mark.asyncio
async def test_get_student_invalid_id():
    """Test que usa un ID inválido (negativo)."""
    async with LifespanManager(app):
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/students/-1")

    assert response.status_code == 422  # Validación de Path(gt=0)


def test_get_student_invalid_id():
    """Test que usa un ID inválido (negativo)."""
    with TestClient(app) as client:
        response = client.get("/students/-1")

    assert response.status_code == 422  # Validación de Path(gt=0)
