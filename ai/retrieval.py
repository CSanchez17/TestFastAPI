from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models import Location, Room
from .config import get_ai_settings

try:
    import chromadb
except Exception:  # pragma: no cover - optional runtime dependency in tests/CI
    chromadb = None

QUIET_KEYWORDS = ["quiet", "silence", "silent", "tranquilo", "calm"]
WORK_KEYWORDS = ["work", "desk", "workspace", "office", "trabajar", "escritorio"]
CENTER_KEYWORDS = ["center", "central", "centro"]


async def collect_rooms(session) -> list[Room]:
    """Load available rooms with locations for retrieval and ranking."""
    stmt = (
        select(Room)
        .options(selectinload(Room.location))
        .where(Room.is_available.is_(True))
        .order_by(Room.id)
    )
    return (await session.execute(stmt)).scalars().all()


async def collect_known_locations(session) -> tuple[list[str], list[str]]:
    """Load known city and country names to improve prompt parsing."""
    locations = (await session.execute(select(Location))).scalars().all()
    cities = sorted({location.city for location in locations if location.city})
    countries = sorted({location.country for location in locations if location.country})
    return cities, countries


def normalize(text: str) -> str:
    return text.strip().lower()


def extract_max_price(prompt: str) -> float | None:
    """Extract a budget hint from free-form user text."""
    patterns = [
        r"(?:max(?:imum)?|hasta|under|below|less than|no pase de)\s*(\d+(?:[\.,]\d+)?)",
        r"(\d+(?:[\.,]\d+)?)\s*(?:€|eur|euros?)",
    ]
    lowered = prompt.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return float(match.group(1).replace(",", "."))
    return None


def extract_preferences(prompt: str, known_cities: list[str], known_countries: list[str]) -> dict[str, Any]:
    """Translate natural language into simple retrieval preferences."""
    lowered = normalize(prompt)

    city = next((c for c in known_cities if normalize(c) in lowered), None)
    country = next((c for c in known_countries if normalize(c) in lowered), None)

    return {
        "max_price": extract_max_price(prompt),
        "needs_quiet": any(keyword in lowered for keyword in QUIET_KEYWORDS),
        "needs_work": any(keyword in lowered for keyword in WORK_KEYWORDS),
        "near_center": any(keyword in lowered for keyword in CENTER_KEYWORDS),
        "city": city,
        "country": country,
    }


def format_preferences(preferences: dict[str, Any]) -> dict[str, Any]:
    """Expose normalized preference data back to the API layer."""
    return {
        "max_price": preferences.get("max_price"),
        "needs_quiet": preferences.get("needs_quiet", False),
        "needs_work": preferences.get("needs_work", False),
        "near_center": preferences.get("near_center", False),
        "city": preferences.get("city"),
        "country": preferences.get("country"),
    }


def build_reason(metadata: dict[str, Any], preferences: dict[str, Any]) -> str:
    """Create a transparent explanation for each recommended room."""
    reasons: list[str] = []

    if preferences.get("max_price") is not None:
        reasons.append(f"price {metadata['price_per_night']:.0f} EUR/night is within your budget")
    if preferences.get("needs_work") and metadata.get("has_workspace"):
        reasons.append("it mentions workspace-friendly features")
    if preferences.get("needs_quiet") and metadata.get("is_quiet"):
        reasons.append("description suggests a quiet environment")
    if preferences.get("near_center") and metadata.get("near_center"):
        reasons.append("it looks close to the city center")
    if metadata.get("city") and metadata.get("country"):
        reasons.append(f"location: {metadata['city']}, {metadata['country']}")

    return "; ".join(reasons) if reasons else "good semantic match for your request"


def score_metadata(metadata: dict[str, Any], preferences: dict[str, Any]) -> float:
    """Score room metadata against extracted preferences.

    This transparent heuristic is also used after vector search to re-rank the
    final candidates.
    """
    score = 0.0

    if preferences.get("needs_quiet") and metadata.get("is_quiet"):
        score += 2.0
    if preferences.get("needs_work") and metadata.get("has_workspace"):
        score += 2.0
    if preferences.get("near_center") and metadata.get("near_center"):
        score += 1.5

    max_price = preferences.get("max_price")
    if max_price is not None and metadata.get("price_per_night") is not None and metadata["price_per_night"] <= max_price:
        score += 2.0
    if preferences.get("city") and metadata.get("city") == preferences["city"]:
        score += 1.5
    if preferences.get("country") and metadata.get("country") == preferences["country"]:
        score += 1.0

    return score


def build_room_metadata(room: Room) -> dict[str, Any]:
    """Flatten a room ORM object into metadata consumable by retrieval layers."""
    location = room.location
    text = " ".join(
        [
            room.title or "",
            room.description or "",
            location.city if location else "",
            location.country if location else "",
            location.address_line if location else "",
        ]
    ).lower()
    return {
        "room_id": int(room.id),
        "title": room.title,
        "price_per_night": float(room.price_per_night),
        "city": location.city if location else "",
        "country": location.country if location else "",
        "has_workspace": any(k in text for k in WORK_KEYWORDS),
        "is_quiet": any(k in text for k in QUIET_KEYWORDS),
        "near_center": any(k in text for k in CENTER_KEYWORDS),
        "document": text,
    }


def build_where_clause(preferences: dict[str, Any]) -> dict[str, Any] | None:
    """Map structured preferences to Chroma metadata filters."""
    clauses: list[dict[str, Any]] = []
    if preferences.get("max_price") is not None:
        clauses.append({"price_per_night": {"$lte": float(preferences["max_price"])}})
    if preferences.get("city"):
        clauses.append({"city": preferences["city"]})
    if preferences.get("country"):
        clauses.append({"country": preferences["country"]})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def render_recommendations(items: list[dict[str, Any]], preferences: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert internal metadata objects into stable API recommendation payloads."""
    return [
        {
            "room_id": int(item["room_id"]),
            "title": item.get("title", ""),
            "price_per_night": float(item.get("price_per_night", 0)),
            "city": item.get("city", ""),
            "country": item.get("country", ""),
            "reason": build_reason(item, preferences),
        }
        for item in items
    ]


def rank_rooms_locally(rooms: list[Room], preferences: dict[str, Any], max_results: int) -> list[dict[str, Any]]:
    """Fallback ranking path when Chroma or embeddings are unavailable."""
    ranked: list[dict[str, Any]] = []
    for room in rooms:
        metadata = build_room_metadata(room)
        metadata["score"] = score_metadata(metadata, preferences)
        ranked.append(metadata)

    ranked.sort(key=lambda item: item.get("score", 0), reverse=True)
    return render_recommendations(ranked[:max_results], preferences)


def upsert_rooms_in_chroma(collection, rooms: list[Room]) -> None:
    """Synchronize the current room catalog into Chroma before querying."""
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for room in rooms:
        metadata = build_room_metadata(room)
        ids.append(str(room.id))
        documents.append(metadata.pop("document"))
        metadatas.append(metadata)

    if ids:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)


def rank_rooms_with_chroma(rooms: list[Room], query: str, preferences: dict[str, Any], max_results: int) -> list[dict[str, Any]]:
    """Vector-search ranking path backed by ChromaDB."""
    if chromadb is None:
        return rank_rooms_locally(rooms, preferences, max_results)

    settings = get_ai_settings()
    client = chromadb.PersistentClient(path=str(settings.chroma_path))
    collection = client.get_or_create_collection(name=settings.chroma_collection)
    upsert_rooms_in_chroma(collection, rooms)

    result = collection.query(
        query_texts=[query],
        n_results=max(max_results * 3, 6),
        where=build_where_clause(preferences),
    )

    metadatas = result.get("metadatas", [[]])[0]
    unique_by_id: dict[int, dict[str, Any]] = {}
    for metadata in metadatas:
        room_id = int(metadata["room_id"])
        metadata["score"] = score_metadata(metadata, preferences)
        unique_by_id[room_id] = metadata

    ranked = sorted(unique_by_id.values(), key=lambda item: item.get("score", 0), reverse=True)
    if not ranked:
        return rank_rooms_locally(rooms, preferences, max_results)

    return render_recommendations(ranked[:max_results], preferences)
