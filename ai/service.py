from __future__ import annotations

from .llm import generate_concierge_message
from .retrieval import (
    collect_known_locations,
    collect_rooms,
    extract_preferences,
    format_preferences,
    rank_rooms_locally,
    rank_rooms_with_chroma,
)


async def recommend_rooms(session, query: str, max_results: int = 3) -> dict:
    """Application service for the room concierge use case.

    Responsibilities:
    - gather domain data from the database,
    - translate user text into retrieval preferences,
    - retrieve and rank room candidates,
    - generate the final assistant summary.

    This orchestration layer is intentionally small so future AI capabilities can
    reuse retrieval and generation modules without being tied to this endpoint.
    """
    rooms = await collect_rooms(session)
    if not rooms:
        return {
            "query": query,
            "extracted_preferences": format_preferences({}),
            "assistant_message": await generate_concierge_message(query, []),
            "recommendations": [],
        }

    known_cities, known_countries = await collect_known_locations(session)
    preferences = extract_preferences(query, known_cities, known_countries)

    recommendations = rank_rooms_with_chroma(rooms, query, preferences, max_results)
    if not recommendations:
        recommendations = rank_rooms_locally(rooms, preferences, max_results)

    return {
        "query": query,
        "extracted_preferences": format_preferences(preferences),
        "assistant_message": await generate_concierge_message(query, recommendations),
        "recommendations": recommendations,
    }
