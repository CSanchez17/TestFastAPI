import json

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
    assert prefs["country"] == "Germany"  # resolved via COUNTRY_ALIASES

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
    async def fake_generate(query, recommendations, output_language=None, preferences=None):
        assert query
        return {"message": "Mocked assistant summary", "suggested_queries": []}

    async def fake_detect_and_translate(text):
        return {"language": "en", "translation": text}

    async def fake_translate_recs(recs, target_language):
        return recs

    monkeypatch.setattr("ai.service.generate_concierge_message", fake_generate)
    monkeypatch.setattr("ai.service.detect_and_translate", fake_detect_and_translate)
    monkeypatch.setattr("ai.service.translate_recommendations", fake_translate_recs)

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


def test_multilingual_query_german_picks_italy():
    import asyncio

    async def run_case():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
        session_maker = async_sessionmaker(engine, expire_on_commit=False)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            user = User(
                username='host1',
                email='h1@example.com',
                hashed_password='x',
                is_host=True,
                is_active=True,
                is_superuser=False,
                is_verified=True,
            )
            session.add(user)
            await session.flush()

            loc_pt = Location(address_line='Rua A', city='Lisbon', country='Portugal', postal_code='1000')
            session.add(loc_pt)
            await session.flush()
            room_pt = Room(title='Lisbon Room', location_id=loc_pt.id, description='Nice', price_per_night=85, is_available=True, owner_id=user.id)
            session.add(room_pt)

            loc_it = Location(address_line='Via C', city='Rome', country='Italy', postal_code='00100')
            session.add(loc_it)
            await session.flush()
            room_it = Room(title='Rome Cheap', location_id=loc_it.id, description='Cheap', price_per_night=25, is_available=True, owner_id=user.id)
            session.add(room_it)

            await session.commit()

        # Disable chroma for deterministic local ranking
        from ai import retrieval
        retrieval.chromadb = None

        # Patch detect_and_translate to simulate LLM detection+translation
        from ai import llm, service

        async def fake_detect_and_translate(text):
            return {"language": "de", "translation": "the cheapest room in italy"}

        llm.detect_and_translate = fake_detect_and_translate
        service.detect_and_translate = fake_detect_and_translate

        # Patch translate_recommendations to return recs unchanged (no real LLM)
        async def fake_translate_recs(recs, target_language):
            return recs

        llm.translate_recommendations = fake_translate_recs
        service.translate_recommendations = fake_translate_recs

        async with session_maker() as session:
            result = await recommend_rooms(session=session, query='Das günstigste Zimmer in Italien', max_results=3)
        await engine.dispose()
        return result

    res = asyncio.run(run_case())
    # The top recommendation should be the Italy room
    assert res['recommendations'][0]['country'].lower().startswith('ital')


def test_multilingual_query_spanish_picks_spain():
    import asyncio

    async def run_case():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
        session_maker = async_sessionmaker(engine, expire_on_commit=False)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            user = User(
                username='host2',
                email='h2@example.com',
                hashed_password='x',
                is_host=True,
                is_active=True,
                is_superuser=False,
                is_verified=True,
            )
            session.add(user)
            await session.flush()

            loc_pt = Location(address_line='Rua A', city='Lisbon', country='Portugal', postal_code='1000')
            session.add(loc_pt)
            await session.flush()
            room_pt = Room(title='Lisbon Room', location_id=loc_pt.id, description='Nice', price_per_night=85, is_available=True, owner_id=user.id)
            session.add(room_pt)

            loc_es = Location(address_line='Calle B', city='Madrid', country='España', postal_code='28001')
            session.add(loc_es)
            await session.flush()
            room_es = Room(title='Madrid Cheap', location_id=loc_es.id, description='Cheap', price_per_night=30, is_available=True, owner_id=user.id)
            session.add(room_es)

            await session.commit()

        from ai import retrieval
        retrieval.chromadb = None

        from ai import llm, service

        async def fake_detect_and_translate(text):
            return {"language": "es", "translation": "the cheapest hotel in espana"}

        llm.detect_and_translate = fake_detect_and_translate
        service.detect_and_translate = fake_detect_and_translate

        async def fake_translate_recs(recs, target_language):
            return recs

        llm.translate_recommendations = fake_translate_recs
        service.translate_recommendations = fake_translate_recs

        async with session_maker() as session:
            result = await recommend_rooms(session=session, query='dame el hotel con el precio mas bajo en espana', max_results=3)
        await engine.dispose()
        return result

    res = asyncio.run(run_case())
    assert res['recommendations'][0]['country'].lower().startswith('esp') or res['recommendations'][0]['country'].lower().startswith('spa')


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests for ai.retrieval helpers
# ═══════════════════════════════════════════════════════════════════════════════

from ai.retrieval import normalize, COUNTRY_ALIASES, build_room_metadata, score_metadata, build_reason


class TestNormalize:
    def test_strips_diacritics(self):
        assert normalize("España") == "espana"

    def test_lowercases(self):
        assert normalize("BERLIN") == "berlin"

    def test_strips_whitespace(self):
        assert normalize("  Rome  ") == "rome"

    def test_handles_none(self):
        assert normalize(None) == ""

    def test_german_umlauts(self):
        assert normalize("München") == "munchen"

    def test_combined(self):
        assert normalize("  São Paulo  ") == "sao paulo"


class TestExtractPreferencesCountryAliases:
    """Validate the COUNTRY_ALIASES fallback in extract_preferences."""

    def test_alias_deutschland_maps_to_germany(self):
        prefs = extract_preferences(
            "cheapest room in deutschland",
            known_cities=[],
            known_countries=["Germany"],
        )
        assert prefs["country"] == "Germany"

    def test_alias_espana_maps_to_espana_entry(self):
        prefs = extract_preferences(
            "hotel barato en espana",
            known_cities=[],
            known_countries=["España"],
        )
        assert prefs["country"] == "España"

    def test_alias_italy_maps_to_italia_entry(self):
        prefs = extract_preferences(
            "a room in italy please",
            known_cities=[],
            known_countries=["Italia"],
        )
        assert prefs["country"] == "Italia"

    def test_direct_match_takes_precedence(self):
        """When the DB country name appears literally in the query, no alias needed."""
        prefs = extract_preferences(
            "room in Germany",
            known_cities=[],
            known_countries=["Germany"],
        )
        assert prefs["country"] == "Germany"

    def test_no_country_match_returns_none(self):
        prefs = extract_preferences(
            "a nice room somewhere",
            known_cities=[],
            known_countries=["Germany", "España"],
        )
        assert prefs["country"] is None

    def test_quiet_and_work_keywords(self):
        prefs = extract_preferences(
            "quiet desk room in berlin under 100 EUR",
            known_cities=["Berlin"],
            known_countries=["Germany"],
        )
        assert prefs["needs_quiet"] is True
        assert prefs["needs_work"] is True
        assert prefs["max_price"] == 100
        assert prefs["city"] == "Berlin"

    def test_cheapest_keyword(self):
        prefs = extract_preferences(
            "the cheapest room",
            known_cities=[],
            known_countries=[],
        )
        assert prefs["prefer_cheapest"] is True

    @pytest.mark.parametrize("phrase", [
        "the cheapest room in italy",
        "lowest price hotel in italy",
        "most affordable room",
        "budget hotel in spain",
        "give me the hotel with the lowest price in italy",
        "find me an affordable room in rome",
        "economy room in berlin",
    ])
    def test_prefer_cheapest_detected_for_budget_phrases(self, phrase):
        prefs = extract_preferences(phrase, known_cities=[], known_countries=[])
        assert prefs["prefer_cheapest"] is True, f"prefer_cheapest not detected for: {phrase!r}"


class TestCheapestRoomOrdering:
    """The cheapest room must appear first when the user asks for lowest price."""

    def test_cheapest_room_ranked_first(self, monkeypatch):
        import asyncio
        from ai import retrieval, service

        monkeypatch.setattr(retrieval, "chromadb", None)

        async def fake_detect(text):
            return {"language": "de", "translation": "give me the hotel with the lowest price in italy"}

        async def fake_translate_recs(recs, target_language):
            return recs

        async def fake_generate(query, recs, output_language=None, preferences=None):
            return {"message": "Mock summary", "suggested_queries": []}

        monkeypatch.setattr(service, "detect_and_translate", fake_detect)
        monkeypatch.setattr(service, "translate_recommendations", fake_translate_recs)
        monkeypatch.setattr(service, "generate_concierge_message", fake_generate)

        async def run():
            engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
            sm = async_sessionmaker(engine, expire_on_commit=False)

            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async with sm() as session:
                user = User(
                    username="host_cheap", email="cheap@example.com",
                    hashed_password="x", is_host=True, is_active=True,
                    is_superuser=False, is_verified=True,
                )
                session.add(user)
                await session.flush()

                for title, price in [("Cozy Apartment", 85), ("Luxury Suite", 150), ("Budget Studio", 55)]:
                    loc = Location(address_line="Via X", city="Rome", country="Italy", postal_code="00100")
                    session.add(loc)
                    await session.flush()
                    session.add(Room(
                        title=title, location_id=loc.id, description=f"{title} desc",
                        price_per_night=price, is_available=True, owner_id=user.id,
                    ))
                await session.commit()

            async with sm() as session:
                result = await recommend_rooms(session, "gib mir das günstigste Zimmer in Italien", max_results=3)
            await engine.dispose()
            return result

        res = asyncio.run(run())
        recs = res["recommendations"]
        assert len(recs) == 3
        assert recs[0]["price_per_night"] == 55.0, (
            f"Expected cheapest (55) first, got {recs[0]['price_per_night']}"
        )
        assert recs[0]["title"] == "Budget Studio"


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests for ai.llm functions
# ═══════════════════════════════════════════════════════════════════════════════

import json
import ai.llm as _ai_llm_module
import ai.service as _ai_service_module
from ai.llm import (
    _call_llm,
    _DETECT_CACHE,
    _TRANSLATE_CACHE,
    detect_and_translate,
    translate_text,
    translate_recommendations,
    build_fallback_message,
    generate_concierge_message,
)
from ai.config import AISettings


def _make_settings(provider: str = "none", premium_i18n: bool = False) -> AISettings:
    """Create AISettings with a specific provider for deterministic tests."""
    return AISettings(
        llm_provider=provider,
        cloud_llm_api_key=None,  # prevent real cloud calls
        premium_i18n=premium_i18n,
    )


class TestCallLlm:
    """Tests for _call_llm provider routing."""

    @pytest.mark.asyncio
    async def test_returns_none_when_provider_is_none(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("none"))
        result = await _call_llm("hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_auto_tries_cloud_then_local(self, monkeypatch):
        """With auto, if cloud fails, local should be tried."""
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("auto"))

        call_log = []

        async def fake_cloud(prompt):
            call_log.append("cloud")
            raise Exception("cloud down")

        async def fake_local(prompt):
            call_log.append("local")
            return "local response"

        monkeypatch.setattr(_ai_llm_module, "call_cloud_llm", fake_cloud)
        monkeypatch.setattr(_ai_llm_module, "call_local_llm", fake_local)

        result = await _call_llm("test")
        assert result == "local response"
        assert call_log == ["cloud", "local"]

    @pytest.mark.asyncio
    async def test_cloud_only_returns_none_on_failure(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("cloud"))

        async def fake_cloud(prompt):
            raise Exception("cloud down")

        monkeypatch.setattr(_ai_llm_module, "call_cloud_llm", fake_cloud)

        result = await _call_llm("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_local_only_returns_content(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("local"))

        async def fake_local(prompt):
            return "  llm says hi  "

        monkeypatch.setattr(_ai_llm_module, "call_local_llm", fake_local)

        result = await _call_llm("test")
        assert result == "llm says hi"


class TestDetectAndTranslate:
    """Tests for detect_and_translate()."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        _DETECT_CACHE.clear()
        yield
        _DETECT_CACHE.clear()

    @pytest.mark.asyncio
    async def test_fallback_when_no_llm(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("none"))
        result = await detect_and_translate("hola mundo")
        assert result == {"language": "en", "translation": "hola mundo"}

    @pytest.mark.asyncio
    async def test_parses_valid_json(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("local"))

        async def fake_local(prompt):
            return json.dumps({"language": "es", "translation": "hello world"})

        monkeypatch.setattr(_ai_llm_module, "call_local_llm", fake_local)

        result = await detect_and_translate("hola mundo")
        assert result["language"] == "es"
        assert result["translation"] == "hello world"

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("local"))

        async def fake_local(prompt):
            return '```json\n{"language": "fr", "translation": "a room in paris"}\n```'

        monkeypatch.setattr(_ai_llm_module, "call_local_llm", fake_local)

        result = await detect_and_translate("une chambre à paris")
        assert result["language"] == "fr"
        assert result["translation"] == "a room in paris"

    @pytest.mark.asyncio
    async def test_malformed_json_returns_fallback(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("local"))

        async def fake_local(prompt):
            return "This is not JSON at all"

        monkeypatch.setattr(_ai_llm_module, "call_local_llm", fake_local)

        result = await detect_and_translate("bonjour")
        assert result == {"language": "en", "translation": "bonjour"}

    @pytest.mark.asyncio
    async def test_caches_result(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("local"))

        call_count = 0

        async def fake_local(prompt):
            nonlocal call_count
            call_count += 1
            return json.dumps({"language": "de", "translation": "hello"})

        monkeypatch.setattr(_ai_llm_module, "call_local_llm", fake_local)

        r1 = await detect_and_translate("hallo")
        r2 = await detect_and_translate("hallo")
        assert r1 == r2
        assert call_count == 1  # second call served from cache

    @pytest.mark.asyncio
    async def test_english_input(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("local"))

        async def fake_local(prompt):
            return json.dumps({"language": "en", "translation": "cheap room in berlin"})

        monkeypatch.setattr(_ai_llm_module, "call_local_llm", fake_local)

        result = await detect_and_translate("cheap room in berlin")
        assert result["language"] == "en"
        assert result["translation"] == "cheap room in berlin"


class TestTranslateText:
    """Tests for translate_text() backward-compat function."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        _TRANSLATE_CACHE.clear()
        yield
        _TRANSLATE_CACHE.clear()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_llm(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("none"))
        result = await translate_text("hello", "es")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_translated_text(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("local"))

        async def fake_local(prompt):
            return "hola"

        monkeypatch.setattr(_ai_llm_module, "call_local_llm", fake_local)

        result = await translate_text("hello", "es")
        assert result == "hola"

    @pytest.mark.asyncio
    async def test_caches_translation(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("local"))
        call_count = 0

        async def fake_local(prompt):
            nonlocal call_count
            call_count += 1
            return "bonjour"

        monkeypatch.setattr(_ai_llm_module, "call_local_llm", fake_local)

        r1 = await translate_text("hello", "fr")
        r2 = await translate_text("hello", "fr")
        assert r1 == r2 == "bonjour"
        assert call_count == 1


class TestTranslateRecommendations:
    """Tests for translate_recommendations()."""

    SAMPLE_RECS = [
        {
            "room_id": 1,
            "title": "Cozy Berlin Room",
            "description": "A warm and welcoming room in central Berlin.",
            "price_per_night": 65.0,
            "city": "Berlin",
            "country": "Germany",
            "reason": "good match for your request",
        },
    ]

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self):
        result = await translate_recommendations([], "es")
        assert result == []

    @pytest.mark.asyncio
    async def test_english_target_returns_as_is(self):
        result = await translate_recommendations(self.SAMPLE_RECS, "en")
        assert result is self.SAMPLE_RECS  # same object, no copy

    @pytest.mark.asyncio
    async def test_translates_fields(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("local"))

        async def fake_local(prompt):
            return json.dumps([{
                "title": "Habitación acogedora en Berlín",
                "description": "Una habitación cálida y acogedora en el centro de Berlín.",
                "city": "Berlín",
                "country": "Alemania",
            }])

        monkeypatch.setattr(_ai_llm_module, "call_local_llm", fake_local)

        result = await translate_recommendations(self.SAMPLE_RECS, "es")
        assert result[0]["title"] == "Habitación acogedora en Berlín"
        assert result[0]["description"] == "Una habitación cálida y acogedora en el centro de Berlín."
        assert result[0]["city"] == "Berlín"
        assert result[0]["country"] == "Alemania"
        assert result[0]["room_id"] == 1  # numeric fields preserved
        assert result[0]["price_per_night"] == 65.0

    @pytest.mark.asyncio
    async def test_malformed_json_returns_originals(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("local"))

        async def fake_local(prompt):
            return "I can't translate that"

        monkeypatch.setattr(_ai_llm_module, "call_local_llm", fake_local)

        result = await translate_recommendations(self.SAMPLE_RECS, "de")
        assert result == self.SAMPLE_RECS

    @pytest.mark.asyncio
    async def test_mismatched_array_length_returns_originals(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("local"))

        async def fake_local(prompt):
            return json.dumps([
                {"title": "A", "description": "B", "city": "C", "country": "D"},
                {"title": "E", "description": "F", "city": "G", "country": "H"},
            ])

        monkeypatch.setattr(_ai_llm_module, "call_local_llm", fake_local)

        result = await translate_recommendations(self.SAMPLE_RECS, "de")
        assert result == self.SAMPLE_RECS  # length mismatch -> fallback

    @pytest.mark.asyncio
    async def test_no_llm_returns_originals(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("none"))
        result = await translate_recommendations(self.SAMPLE_RECS, "fr")
        assert result == self.SAMPLE_RECS

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("local"))

        async def fake_local(prompt):
            return '```json\n[{"title":"Zimmer","description":"Ein warmes Zimmer","city":"Berlin","country":"Deutschland"}]\n```'

        monkeypatch.setattr(_ai_llm_module, "call_local_llm", fake_local)

        result = await translate_recommendations(self.SAMPLE_RECS, "de")
        assert result[0]["title"] == "Zimmer"
        assert result[0]["country"] == "Deutschland"


class TestBuildFallbackMessage:
    def test_no_recommendations(self):
        msg = build_fallback_message("any query", [])
        assert "could not find" in msg.lower()

    def test_with_recommendations(self):
        recs = [
            {
                "title": "Nice Room",
                "city": "Madrid",
                "country": "Spain",
                "price_per_night": 50.0,
                "reason": "good match",
            }
        ]
        msg = build_fallback_message("hotel in spain", recs)
        assert "Nice Room" in msg
        assert "Madrid" in msg
        assert "50" in msg


class TestGenerateConciergeMessage:
    @pytest.mark.asyncio
    async def test_fallback_when_none_provider(self, monkeypatch):
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("none"))
        recs = [
            {
                "title": "Test Room",
                "city": "Rome",
                "country": "Italy",
                "price_per_night": 40.0,
                "reason": "affordable",
            }
        ]
        result = await generate_concierge_message("room in italy", recs)
        assert isinstance(result, dict)
        assert "Test Room" in result["message"]
        assert "Rome" in result["message"]
        assert isinstance(result.get("suggested_queries"), list)


# ═══════════════════════════════════════════════════════════════════════════════
# Suggested follow-up queries tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildFallbackSuggestions:
    """Unit tests for the deterministic fallback suggestion generator."""

    def test_returns_three_suggestions(self):
        from ai.llm import build_fallback_suggestions
        recs = [{"city": "Rome", "country": "Italy", "price_per_night": 50}]
        result = build_fallback_suggestions("cheap room in italy", recs)
        assert len(result) == 3

    def test_country_in_suggestions(self):
        from ai.llm import build_fallback_suggestions
        recs = [{"city": "Rome", "country": "Italy", "price_per_night": 50}]
        result = build_fallback_suggestions("room in italy", recs, preferences={"country": "Italy"})
        assert any("Italy" in s for s in result)

    def test_city_in_suggestions(self):
        from ai.llm import build_fallback_suggestions
        recs = [{"city": "Berlin", "country": "Germany", "price_per_night": 45}]
        result = build_fallback_suggestions("room in berlin", recs, preferences={"city": "Berlin"})
        assert any("Berlin" in s for s in result)

    def test_quiet_suggestion_when_not_quiet(self):
        from ai.llm import build_fallback_suggestions
        recs = [{"city": "Paris", "country": "France"}]
        result = build_fallback_suggestions("room in paris", recs, preferences={})
        assert any("quiet" in s.lower() for s in result)

    def test_workspace_suggestion_when_quiet_but_not_work(self):
        from ai.llm import build_fallback_suggestions
        recs = [{"city": "Paris", "country": "France"}]
        result = build_fallback_suggestions("quiet room", recs, preferences={"needs_quiet": True})
        assert any("workspace" in s.lower() for s in result)

    def test_view_suggestion_when_both_quiet_and_work(self):
        from ai.llm import build_fallback_suggestions
        recs = [{"city": "Madrid", "country": "Spain"}]
        result = build_fallback_suggestions("q", recs, preferences={"needs_quiet": True, "needs_work": True})
        assert any("balcony" in s.lower() or "view" in s.lower() for s in result)

    def test_no_preferences_still_returns_suggestions(self):
        from ai.llm import build_fallback_suggestions
        result = build_fallback_suggestions("any room please", [])
        assert len(result) == 3


class TestExtractConciergeResult:
    """Unit tests for _extract_concierge_result."""

    @pytest.mark.asyncio
    async def test_valid_json_returns_message_and_suggestions(self, monkeypatch):
        from ai.llm import _extract_concierge_result
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("none"))
        raw = json.dumps({
            "summary": "Great room for you.",
            "top_recommendation": {"title": "Test Room", "city": "Rome", "country": "Italy", "price_per_night": 40},
            "suggested_queries": ["Try Barcelona?", "Cheaper options?", "Quiet rooms?"],
        })
        recs = [{"title": "Test Room", "city": "Rome", "country": "Italy", "price_per_night": 40}]
        result = await _extract_concierge_result(raw, "room in italy", recs)
        assert result is not None
        assert result["message"] == "Great room for you."
        assert len(result["suggested_queries"]) == 3

    @pytest.mark.asyncio
    async def test_markdown_fences_stripped(self, monkeypatch):
        from ai.llm import _extract_concierge_result
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("none"))
        raw = "```json\n" + json.dumps({
            "summary": "OK",
            "top_recommendation": {"title": "R", "city": "C", "country": "X", "price_per_night": 10},
            "suggested_queries": [],
        }) + "\n```"
        recs = [{"title": "R", "price_per_night": 10}]
        result = await _extract_concierge_result(raw, "q", recs)
        assert result is not None
        assert result["message"] == "OK"

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self, monkeypatch):
        from ai.llm import _extract_concierge_result
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("none"))
        raw = json.dumps({
            "summary": "Wrong room.",
            "top_recommendation": {"title": "Unknown Room", "city": "X", "country": "Y", "price_per_night": 999},
            "suggested_queries": [],
        })
        recs = [{"title": "Real Room", "price_per_night": 50}]
        result = await _extract_concierge_result(raw, "q", recs)
        assert result is None

    @pytest.mark.asyncio
    async def test_raw_text_fallback(self, monkeypatch):
        from ai.llm import _extract_concierge_result
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("none"))
        recs = [{"city": "Rome", "country": "Italy"}]
        result = await _extract_concierge_result("Just a plain text answer.", "room in italy", recs)
        assert result is not None
        assert result["message"] == "Just a plain text answer."
        assert isinstance(result["suggested_queries"], list)

    @pytest.mark.asyncio
    async def test_empty_suggestions_get_replaced_by_fallback(self, monkeypatch):
        from ai.llm import _extract_concierge_result
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("none"))
        raw = json.dumps({
            "summary": "Here you go.",
            "top_recommendation": {"title": "Room A", "city": "Berlin", "country": "Germany", "price_per_night": 45},
            "suggested_queries": [],
        })
        recs = [{"title": "Room A", "city": "Berlin", "country": "Germany", "price_per_night": 45}]
        result = await _extract_concierge_result(raw, "room in berlin", recs)
        assert result is not None
        assert len(result["suggested_queries"]) == 3  # fallback fills them in


class TestTranslateSuggestions:
    """Unit tests for _translate_suggestions."""

    @pytest.mark.asyncio
    async def test_skips_translation_for_english(self, monkeypatch):
        from ai.llm import _translate_suggestions
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("none"))
        original = ["Show me cheaper rooms", "Any quiet rooms?", "Try Barcelona"]
        result = await _translate_suggestions(original, "en")
        assert result == original

    @pytest.mark.asyncio
    async def test_skips_translation_when_no_language(self, monkeypatch):
        from ai.llm import _translate_suggestions
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("none"))
        original = ["Show me cheaper rooms"]
        result = await _translate_suggestions(original, None)
        assert result == original

    @pytest.mark.asyncio
    async def test_returns_originals_when_no_llm(self, monkeypatch):
        from ai.llm import _translate_suggestions
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("none"))
        original = ["Show me cheaper rooms", "Any quiet rooms?"]
        result = await _translate_suggestions(original, "fr")
        # With provider=none, _call_llm returns None => originals returned
        assert result == original

    @pytest.mark.asyncio
    async def test_translates_when_llm_available(self, monkeypatch):
        from ai.llm import _translate_suggestions
        translated_json = json.dumps(["Habitaciones más baratas", "¿Habitaciones tranquilas?", "¿Prueba Barcelona?"])

        async def fake_call_llm(prompt):
            return translated_json

        monkeypatch.setattr(_ai_llm_module, "_call_llm", fake_call_llm)
        original = ["Show me cheaper rooms", "Any quiet rooms?", "Try Barcelona?"]
        result = await _translate_suggestions(original, "es")
        assert result == ["Habitaciones más baratas", "¿Habitaciones tranquilas?", "¿Prueba Barcelona?"]

    @pytest.mark.asyncio
    async def test_returns_originals_on_malformed_response(self, monkeypatch):
        from ai.llm import _translate_suggestions

        async def fake_call_llm(prompt):
            return "not valid json"

        monkeypatch.setattr(_ai_llm_module, "_call_llm", fake_call_llm)
        original = ["A", "B", "C"]
        result = await _translate_suggestions(original, "de")
        assert result == original


class TestSuggestedQueriesInResponse:
    """E2E: verify suggested_queries appears in the service response."""

    def test_suggested_queries_present_in_response(self, monkeypatch):
        import asyncio
        from ai import retrieval, service
        retrieval.chromadb = None
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("none"))

        async def fake_detect(text):
            return {"language": "en", "translation": text}

        monkeypatch.setattr(service, "detect_and_translate", fake_detect)
        monkeypatch.setattr(service, "translate_recommendations", lambda recs, **kw: recs)

        async def run():
            engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with sm() as session:
                user = User(username="h", email="h@x.com", hashed_password="x",
                            is_host=True, is_active=True, is_superuser=False, is_verified=True)
                session.add(user)
                await session.flush()
                loc = Location(address_line="A1", city="Rome", country="Italy",
                               postal_code="00100")
                session.add(loc)
                await session.flush()
                room = Room(title="Roman Room", description="Nice", price_per_night=50,
                            is_available=True, location_id=loc.id, owner_id=user.id)
                session.add(room)
                await session.commit()
            async with sm() as session:
                result = await recommend_rooms(session, "cheap room in italy", max_results=2)
            await engine.dispose()
            return result

        res = asyncio.run(run())
        assert "suggested_queries" in res
        assert isinstance(res["suggested_queries"], list)
        assert len(res["suggested_queries"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# End-to-end multilingual service tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMultilingualServiceE2E:
    """Full-flow tests for recommend_rooms with various languages."""

    @staticmethod
    async def _setup_db_with_rooms(rooms_data):
        """Helper: create in-memory DB, seed user + locations + rooms."""
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
        session_maker = async_sessionmaker(engine, expire_on_commit=False)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            user = User(
                username="host_e2e",
                email="e2e@example.com",
                hashed_password="x",
                is_host=True,
                is_active=True,
                is_superuser=False,
                is_verified=True,
            )
            session.add(user)
            await session.flush()

            for rd in rooms_data:
                loc = Location(
                    address_line=rd["address"],
                    city=rd["city"],
                    country=rd["country"],
                    postal_code=rd.get("postal", "00000"),
                )
                session.add(loc)
                await session.flush()
                room = Room(
                    title=rd["title"],
                    location_id=loc.id,
                    description=rd.get("description", ""),
                    price_per_night=rd["price"],
                    is_available=True,
                    owner_id=user.id,
                )
                session.add(room)

            await session.commit()

        return engine, session_maker

    def test_french_query_picks_france(self, monkeypatch):
        """'une chambre pas chère en france' should pick the France room (premium i18n)."""
        import asyncio
        from ai import retrieval, llm, service

        retrieval.chromadb = None
        monkeypatch.setattr(_ai_service_module, "get_ai_settings",
                            lambda: _make_settings(premium_i18n=True))

        async def fake_detect(text):
            return {"language": "fr", "translation": "a cheap room in france"}

        async def fake_translate_recs(recs, target_language):
            for r in recs:
                r["country"] = "France (traduit)"
            return recs

        async def fake_generate(query, recs, output_language=None, preferences=None):
            assert output_language == "fr"
            return {"message": "Voici votre recommandation.", "suggested_queries": []}

        monkeypatch.setattr(service, "detect_and_translate", fake_detect)
        monkeypatch.setattr(service, "translate_recommendations", fake_translate_recs)
        monkeypatch.setattr(service, "generate_concierge_message", fake_generate)

        async def run():
            engine, sm = await self._setup_db_with_rooms([
                {"address": "Rue A", "city": "Paris", "country": "France", "title": "Paris Room", "price": 55},
                {"address": "Via B", "city": "Rome", "country": "Italy", "title": "Rome Room", "price": 60},
            ])
            async with sm() as session:
                result = await recommend_rooms(session, "une chambre pas chère en france", max_results=2, language="fr")
            await engine.dispose()
            return result

        res = asyncio.run(run())
        assert res["recommendations"][0]["country"] == "France (traduit)"
        assert res["assistant_message"] == "Voici votre recommandation."

    def test_english_query_skips_translation(self, monkeypatch):
        """English input should NOT trigger translate_recommendations even with premium."""
        import asyncio
        from ai import retrieval, llm, service

        retrieval.chromadb = None
        monkeypatch.setattr(_ai_service_module, "get_ai_settings",
                            lambda: _make_settings(premium_i18n=True))

        translate_called = False

        async def fake_detect(text):
            return {"language": "en", "translation": text}

        async def fake_translate_recs(recs, target_language):
            nonlocal translate_called
            translate_called = True
            return recs

        async def fake_generate(query, recs, output_language=None, preferences=None):
            assert output_language is None  # no language override for English
            return {"message": "Here is your recommendation.", "suggested_queries": []}

        monkeypatch.setattr(service, "detect_and_translate", fake_detect)
        monkeypatch.setattr(service, "translate_recommendations", fake_translate_recs)
        monkeypatch.setattr(service, "generate_concierge_message", fake_generate)

        async def run():
            engine, sm = await self._setup_db_with_rooms([
                {"address": "Street 1", "city": "Berlin", "country": "Germany", "title": "Berlin Room", "price": 45},
            ])
            async with sm() as session:
                result = await recommend_rooms(session, "cheap room in berlin", max_results=2)
            await engine.dispose()
            return result

        res = asyncio.run(run())
        assert not translate_called
        assert res["assistant_message"] == "Here is your recommendation."

    def test_portuguese_query_picks_portugal(self, monkeypatch):
        """'um quarto barato em portugal' should pick the Portugal room (premium)."""
        import asyncio
        from ai import retrieval, service

        retrieval.chromadb = None
        monkeypatch.setattr(_ai_service_module, "get_ai_settings",
                            lambda: _make_settings(premium_i18n=True))

        async def fake_detect(text):
            return {"language": "pt", "translation": "a cheap room in portugal"}

        async def fake_translate_recs(recs, target_language):
            return recs

        async def fake_generate(query, recs, output_language=None, preferences=None):
            assert output_language == "pt"
            return {"message": "Aqui está a sua recomendação.", "suggested_queries": []}

        monkeypatch.setattr(service, "detect_and_translate", fake_detect)
        monkeypatch.setattr(service, "translate_recommendations", fake_translate_recs)
        monkeypatch.setattr(service, "generate_concierge_message", fake_generate)

        async def run():
            engine, sm = await self._setup_db_with_rooms([
                {"address": "Calle 1", "city": "Madrid", "country": "España", "title": "Madrid Room", "price": 70},
                {"address": "Rua 1", "city": "Lisbon", "country": "Portugal", "title": "Lisbon Room", "price": 40},
            ])
            async with sm() as session:
                result = await recommend_rooms(session, "um quarto barato em portugal", max_results=2, language="pt")
            await engine.dispose()
            return result

        res = asyncio.run(run())
        assert res["recommendations"][0]["country"] == "Portugal"

    def test_empty_room_db_returns_empty_recommendations(self, monkeypatch):
        """When no rooms exist, the result should still be well-formed."""
        import asyncio
        from ai import retrieval, service

        retrieval.chromadb = None
        monkeypatch.setattr(_ai_llm_module, "get_ai_settings", lambda: _make_settings("none"))

        async def fake_detect(text):
            return {"language": "en", "translation": text}

        monkeypatch.setattr(service, "detect_and_translate", fake_detect)

        async def run():
            engine, sm = await self._setup_db_with_rooms([])  # no rooms
            async with sm() as session:
                result = await recommend_rooms(session, "any room please", max_results=3)
            await engine.dispose()
            return result

        res = asyncio.run(run())
        assert res["recommendations"] == []
        assert "could not find" in res["assistant_message"].lower()

    def test_free_tier_skips_translation_for_non_english(self, monkeypatch):
        """Without premium_i18n, non-English queries get English output."""
        import asyncio
        from ai import retrieval, service

        retrieval.chromadb = None
        # premium_i18n defaults to False
        monkeypatch.setattr(_ai_service_module, "get_ai_settings",
                            lambda: _make_settings(premium_i18n=False))

        translate_called = False

        async def fake_detect(text):
            return {"language": "es", "translation": "the cheapest hotel in spain"}

        async def fake_translate_recs(recs, target_language):
            nonlocal translate_called
            translate_called = True
            return recs

        async def fake_generate(query, recs, output_language=None, preferences=None):
            assert output_language is None, "Free tier should not set output_language"
            return {"message": "Here is your recommendation.", "suggested_queries": []}

        monkeypatch.setattr(service, "detect_and_translate", fake_detect)
        monkeypatch.setattr(service, "translate_recommendations", fake_translate_recs)
        monkeypatch.setattr(service, "generate_concierge_message", fake_generate)

        async def run():
            engine, sm = await self._setup_db_with_rooms([
                {"address": "Calle 1", "city": "Madrid", "country": "España",
                 "title": "Madrid Room", "price": 55},
            ])
            async with sm() as session:
                result = await recommend_rooms(
                    session, "dame el hotel más barato en españa",
                    max_results=2, language="es",
                )
            await engine.dispose()
            return result

        res = asyncio.run(run())
        assert not translate_called, "translate_recommendations should not be called on free tier"
        assert res["assistant_message"] == "Here is your recommendation."
        assert res["detected_language"] == "es"  # still detected, just not used for output
