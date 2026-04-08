from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import pytest

from ai.retrieval import extract_preferences, format_preferences
from ai.service import recommend_rooms
from database import Base
from models import Location, Room, User

from .conftest import auth_headers


@pytest.fixture(autouse=True)
def _force_llm_disabled(monkeypatch):
    # Keep AI tests deterministic and independent from external LLM runtimes.
    monkeypatch.setenv("CONCIERGE_LLM_PROVIDER", "none")


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


def test_ai_concierge_public_contract_hides_llm_implementation(client: TestClient):
    host_headers = auth_headers(client, "master", "master")
    activate_host(client, host_headers)

    create_room = client.post(
        "/rooms",
        json={
            "title": "AI Contract Test Room",
            "location": location_payload("Neural Street 42"),
            "description": "Quiet room with desk near center.",
            "price_per_night": 78,
            "is_available": True,
        },
        headers=host_headers,
    )
    assert create_room.status_code == 200

    response = client.post(
        "/ai/concierge",
        json={
            "query": "Need a quiet workspace near center under 80 euro",
            "max_results": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "query" in payload
    assert "extracted_preferences" in payload
    assert "assistant_message" in payload
    assert "recommendations" in payload
    assert "llm_provider_used" not in payload
    assert "llm_model_used" not in payload


def test_ai_concierge_rejects_too_short_query(client: TestClient):
    response = client.post(
        "/ai/concierge",
        json={
            "query": "hi",
            "max_results": 2,
        },
    )

    assert response.status_code == 422


def test_extract_preferences_parses_budget_and_location():
    prompt = "Need a quiet room for work near center in Berlin under 80 EUR"
    prefs = extract_preferences(prompt, known_cities=["Berlin", "Madrid"], known_countries=["Germany", "Spain"])

    assert prefs["max_price"] == 80
    assert prefs["needs_quiet"] is True
    assert prefs["needs_work"] is True
    assert prefs["near_center"] is True
    assert prefs["city"] == "Berlin"
    assert prefs["country"] is None

    formatted = format_preferences(prefs)
    assert formatted["max_price"] == 80
    assert formatted["needs_work"] is True


async def _seed_minimal_room_data(session):
    user = User(
        username="seed_host",
        email="seed_host@example.com",
        hashed_password="fake-hash",
        is_host=True,
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    session.add(user)
    await session.flush()

    location = Location(
        address_line="Seed Street 1",
        city="Berlin",
        country="Germany",
        postal_code="10115",
    )
    session.add(location)
    await session.flush()

    room = Room(
        title="Seed Quiet Room",
        location_id=location.id,
        description="Quiet room with desk near center.",
        price_per_night=79,
        is_available=True,
        owner_id=user.id,
    )
    session.add(room)
    await session.commit()


def test_recommend_rooms_service_builds_response_with_internal_llm_fallback(monkeypatch):
    async def fake_generate(query, recommendations):
        assert query
        return "Mocked assistant summary"

    monkeypatch.setattr("ai.service.generate_concierge_message", fake_generate)

    async def run_case():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
        session_maker = async_sessionmaker(engine, expire_on_commit=False)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            await _seed_minimal_room_data(session)

        async with session_maker() as session:
            result = await recommend_rooms(
                session=session,
                query="quiet room for work under 80 in Berlin",
                max_results=2,
            )

        await engine.dispose()
        return result

    import asyncio

    result = asyncio.run(run_case())
    assert result["assistant_message"] == "Mocked assistant summary"
    assert result["recommendations"]
    assert result["recommendations"][0]["city"] == "Berlin"
