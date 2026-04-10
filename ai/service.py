from __future__ import annotations

import logging

from .config import get_ai_settings
from .llm import (
    detect_and_translate,
    generate_concierge_message,
    translate_recommendations,
    translate_text,
)
from .retrieval import (
    collect_known_locations,
    collect_rooms,
    extract_preferences,
    format_preferences,
    rank_rooms_locally,
    rank_rooms_with_chroma,
)

logger = logging.getLogger(__name__)


async def recommend_rooms(session, query: str, max_results: int = 3, language: str = "en", premium_i18n: bool | None = None) -> dict:
    """Application service for the room concierge use case.

    Flow
    ----
    1. **Detect & translate** – ask the LLM to detect the user's language and,
       if it is not English, translate the query to English.  This single call
       replaces the old ``langdetect`` dependency.
    2. **Extract preferences** from the *English* query and rank rooms.
    3. **Translate recommendations** *(premium only)* – translate room data
       (title, city, country, reason) into the user's language so the UI can
       display localised information.
    4. **Generate assistant message** – build the final concierge summary.
       *(premium)* instructs the LLM to reply in the user's language;
       *(free)* responds in English.
    """
    # Use browser language for all output translation
    output_language = language if language != "en" else None

    # Premium i18n: per-request flag overrides the global config default
    settings = get_ai_settings()
    premium = premium_i18n if premium_i18n is not None else settings.premium_i18n

    rooms = await collect_rooms(session)
    if not rooms:
        no_room_lang = output_language if premium else None
        concierge_result = await generate_concierge_message(query, [], output_language=no_room_lang)
        return {
            "query": query,
            "extracted_preferences": format_preferences({}),
            "assistant_message": concierge_result["message"],
            "recommendations": [],
            "suggested_queries": concierge_result.get("suggested_queries", []),
            "detected_language": language,
        }

    # ── Step 1: detect language & translate to English ────────────────────
    detection = await detect_and_translate(query)
    detected_language = detection["language"]
    english_query = detection["translation"]
    logger.debug(
        "Language detection: lang=%s  english_query=%s",
        detected_language,
        english_query,
    )

    # ── Step 2: extract preferences & rank (all in English) ──────────────
    known_cities, known_countries = await collect_known_locations(session)
    preferences = extract_preferences(english_query, known_cities, known_countries)

    recommendations = rank_rooms_with_chroma(
        rooms, english_query, preferences, max_results
    )
    if not recommendations:
        recommendations = rank_rooms_locally(rooms, preferences, max_results)

    # ── Step 3: translate recommendations (premium only) ─────────────────
    query_output_language = detected_language if detected_language != "en" else None
    localised_recommendations = recommendations  # default: no translation
    if premium and query_output_language:
        localised_recommendations = await translate_recommendations(
            recommendations, target_language=detected_language
        )

    # ── Step 4: generate assistant message ────────────────────────────────
    msg_language = query_output_language if premium else None
    concierge_result = await generate_concierge_message(
        query, localised_recommendations, output_language=msg_language, preferences=preferences
    )

    return {
        "query": query,
        "extracted_preferences": format_preferences(preferences),
        "assistant_message": concierge_result["message"],
        "recommendations": localised_recommendations,
        "suggested_queries": concierge_result.get("suggested_queries", []),
        "detected_language": detected_language,
    }
