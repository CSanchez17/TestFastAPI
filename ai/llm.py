from __future__ import annotations

import json
from typing import Any
from typing import Optional
from pydantic import BaseModel, Field, ValidationError

import httpx

from .config import get_ai_settings
from .prompt_templates import build_concierge_prompt as build_concierge_prompt_template

# Simple in-memory cache keyed by input text.
_DETECT_CACHE: dict[str, dict[str, str]] = {}
_TRANSLATE_CACHE: dict[tuple[str, str], str] = {}


async def _call_llm(prompt: str) -> str | None:
    """Call whichever LLM provider is configured (cloud first, then local)."""
    settings = get_ai_settings()
    provider = (settings.llm_provider or "auto").lower()

    if provider == "none":
        return None

    if provider in ("cloud", "auto"):
        try:
            content = await call_cloud_llm(prompt)
            if content:
                return content.strip()
        except Exception:
            if provider == "cloud":
                return None

    if provider in ("local", "auto"):
        try:
            content = await call_local_llm(prompt)
            if content:
                return content.strip()
        except Exception:
            if provider == "local":
                return None

    return None


async def detect_and_translate(text: str) -> dict[str, str]:
    """Detect the language of *text* and translate it to English in one LLM call.

    Returns ``{"language": "<iso-code>", "translation": "<english text>"}``.
    If the text is already English the translation equals the original.
    Falls back to ``{"language": "en", "translation": text}`` when no LLM is
    available or on any failure.
    """
    fallback = {"language": "en", "translation": text}

    if text in _DETECT_CACHE:
        return _DETECT_CACHE[text]

    prompt = (
        "You receive user text. "
        "1) Detect its language (return the ISO 639-1 two-letter code). "
        "2) If it is NOT English, translate it to English. "
        "3) Return ONLY a JSON object with two keys: \"language\" and \"translation\". "
        "If the text is already English, set \"translation\" to the original text. "
        "Do NOT add any explanation outside the JSON.\n\n"
        f"User text: {text}"
    )

    raw = await _call_llm(prompt)
    if not raw:
        return fallback

    # Strip markdown fences the model might wrap around JSON
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
        result = {
            "language": str(parsed.get("language", "en")).lower().strip(),
            "translation": str(parsed.get("translation", text)).strip(),
        }
        _DETECT_CACHE[text] = result
        return result
    except (json.JSONDecodeError, AttributeError):
        return fallback


async def translate_text(text: str, target_language: str = "en") -> str | None:
    """Translate *text* to *target_language*.  Kept for backward compat."""
    cache_key = (text, target_language)
    if cache_key in _TRANSLATE_CACHE:
        return _TRANSLATE_CACHE[cache_key]

    prompt = (
        f"Translate the following text to {target_language}. "
        "Return ONLY the translated text, no extra explanation.\n\n" + text
    )
    content = await _call_llm(prompt)
    if content:
        _TRANSLATE_CACHE[cache_key] = content
    return content


async def translate_recommendations(
    recommendations: list[dict[str, Any]],
    target_language: str,
) -> list[dict[str, Any]]:
    """Translate user-facing fields in *recommendations* to *target_language*.

    Translates ``title``, ``description``, ``city`` and ``country`` while
    keeping numeric/id fields intact.  Returns new dicts (originals untouched).
    If the LLM is unavailable the recommendations are returned as-is.
    """
    if not recommendations or target_language == "en":
        return recommendations

    texts_to_translate = json.dumps(
        [
            {
                "title": r.get("title", ""),
                "description": r.get("description", ""),
                "city": r.get("city", ""),
                "country": r.get("country", ""),
            }
            for r in recommendations
        ],
        ensure_ascii=False,
    )

    prompt = (
        f"Translate the following JSON array of hotel data to {target_language}. "
        "Keep the same JSON structure. Translate only the string values, keep keys in English. "
        "Return ONLY the translated JSON array, no explanation.\n\n"
        + texts_to_translate
    )

    raw = await _call_llm(prompt)
    if not raw:
        return recommendations

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        translated_items = json.loads(cleaned)
        if not isinstance(translated_items, list) or len(translated_items) != len(recommendations):
            return recommendations

        result = []
        for orig, tr in zip(recommendations, translated_items):
            result.append({
                **orig,
                "title": tr.get("title", orig.get("title", "")),
                "description": tr.get("description", orig.get("description", "")),
                "city": tr.get("city", orig.get("city", "")),
                "country": tr.get("country", orig.get("country", "")),
            })
        return result
    except (json.JSONDecodeError, AttributeError):
        return recommendations


def build_fallback_message(query: str, recommendations: list[dict[str, Any]]) -> str:
    """Return a deterministic summary when no LLM is available.

    This keeps the feature usable in local development and CI even when no
    cloud provider or local runtime is configured.
    """
    if not recommendations:
        return "I could not find matching rooms right now. Try widening your budget or location constraints."

    top = recommendations[0]
    return (
        f"Based on your request '{query}', the best match is {top['title']} in "
        f"{top['city']}, {top['country']} at {top['price_per_night']:.0f} EUR/night. "
        f"Reason: {top['reason']}."
    )


def build_fallback_suggestions(
    query: str,
    recommendations: list[dict[str, Any]],
    preferences: dict[str, Any] | None = None,
) -> list[str]:
    """Generate deterministic follow-up suggestions when no LLM is available."""
    suggestions: list[str] = []
    prefs = preferences or {}

    # Extract context from current results
    cities = sorted({r.get("city", "") for r in recommendations if r.get("city")})
    countries = sorted({r.get("country", "") for r in recommendations if r.get("country")})

    if prefs.get("country") or countries:
        target = prefs.get("country") or (countries[0] if countries else "")
        if target:
            suggestions.append(f"Show me cheaper options in other countries besides {target}")
    else:
        suggestions.append("Show me the cheapest rooms in any country")

    if prefs.get("city") or cities:
        target_city = prefs.get("city") or (cities[0] if cities else "")
        if target_city:
            suggestions.append(f"What about rooms in other cities besides {target_city}?")
    else:
        suggestions.append("Do you have rooms near the city center?")

    if not prefs.get("needs_quiet"):
        suggestions.append("Show me quiet rooms only")
    elif not prefs.get("needs_work"):
        suggestions.append("I need a room with a workspace")
    else:
        suggestions.append("Any rooms with a balcony or nice view?")

    return suggestions[:3]


def build_concierge_prompt(query: str, recommendations: list[dict[str, Any]], output_language: str | None = None) -> str:
    """Delegate prompt construction to `ai.prompt_templates`.

    Centralizing templates simplifies editing, testing and versioning of
    instructions sent to the LLM.
    """
    return build_concierge_prompt_template(query, recommendations, output_language=output_language)


class LLMTopRecommendation(BaseModel):
    title: Optional[str]
    city: Optional[str]
    country: Optional[str]
    price_per_night: Optional[float]


class LLMConciergeOutput(BaseModel):
    summary: str = Field(...)
    top_recommendation: LLMTopRecommendation = Field(...)
    suggested_queries: list[str] = Field(default_factory=list)


async def call_local_llm(prompt: str) -> str | None:
    """Call a local LLM server, for example Ollama running Llama models."""
    settings = get_ai_settings()
    url = f"{settings.local_llm_base_url.rstrip('/')}/api/generate"

    async with httpx.AsyncClient(timeout=settings.local_llm_timeout_seconds) as client:
        response = await client.post(
            url,
            json={
                "model": settings.llm_model or settings.local_llm_model,
                "prompt": prompt,
                "stream": False,
            },
        )
        response.raise_for_status()
        payload = response.json()

    content = payload.get("response")
    return content.strip() if content else None


async def call_cloud_llm(prompt: str) -> str | None:
    """Call a cloud chat-completions style endpoint.

    The implementation defaults to an OpenAI-compatible API shape to keep the
    integration broadly reusable.
    """
    settings = get_ai_settings()
    if not settings.cloud_llm_api_key:
        return None

    url = f"{settings.cloud_llm_base_url.rstrip('/')}/chat/completions"
    async with httpx.AsyncClient(timeout=settings.cloud_llm_timeout_seconds) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.cloud_llm_api_key}"},
            json={
                "model": settings.llm_model or settings.cloud_llm_model,
                "messages": [
                    {"role": "system", "content": "You are a concise booking concierge assistant."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
            },
        )
        response.raise_for_status()
        payload = response.json()

    choices = payload.get("choices") or []
    if not choices:
        return None

    return ((choices[0].get("message") or {}).get("content") or "").strip() or None


async def _translate_suggestions(
    suggestions: list[str], target_language: str | None
) -> list[str]:
    """Translate a list of suggestion strings to *target_language*.

    Uses a single LLM call for efficiency.  Falls back to the originals when
    the LLM is unavailable or the output cannot be parsed.
    """
    if not target_language or target_language == "en" or not suggestions:
        return suggestions

    payload = json.dumps(suggestions, ensure_ascii=False)
    prompt = (
        f"Translate the following JSON array of sentences to {target_language}. "
        "Return ONLY the translated JSON array with the same number of elements. "
        "Do NOT add any explanation outside the JSON.\n\n" + payload
    )
    raw = await _call_llm(prompt)
    if not raw:
        return suggestions

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        translated = json.loads(cleaned)
        if isinstance(translated, list) and len(translated) == len(suggestions):
            return [str(s) for s in translated]
        return suggestions
    except (json.JSONDecodeError, AttributeError):
        return suggestions


async def _make_fallback_result(
    query: str,
    recommendations: list[dict[str, Any]],
    preferences: dict[str, Any] | None = None,
    output_language: str | None = None,
) -> dict[str, Any]:
    """Build a complete fallback result with message + suggestions."""
    suggestions = build_fallback_suggestions(query, recommendations, preferences)
    suggestions = await _translate_suggestions(suggestions, output_language)
    return {
        "message": build_fallback_message(query, recommendations),
        "suggested_queries": suggestions,
    }


async def _extract_concierge_result(
    raw: str,
    query: str,
    recommendations: list[dict[str, Any]],
    preferences: dict[str, Any] | None = None,
    output_language: str | None = None,
) -> dict[str, Any] | None:
    """Try to parse LLM output into a validated concierge result.

    Returns ``{"message": ..., "suggested_queries": [...]}`` on success,
    or *None* when the output cannot be validated (caller should fall back).
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
        validated = LLMConciergeOutput.model_validate(parsed)
        top = validated.top_recommendation.model_dump()
        match = any(
            (
                (rec.get("title") == top.get("title") if top.get("title") else False)
                or (
                    rec.get("price_per_night") == top.get("price_per_night")
                    if top.get("price_per_night") is not None
                    else False
                )
            )
            for rec in recommendations
        )
        if match:
            suggestions = validated.suggested_queries
            if not suggestions:
                suggestions = build_fallback_suggestions(query, recommendations, preferences)
                suggestions = await _translate_suggestions(suggestions, output_language)
            return {"message": validated.summary, "suggested_queries": suggestions}
        return None
    except (json.JSONDecodeError, ValidationError):
        # Raw text from the model — use it as message, generate suggestions deterministically
        suggestions = build_fallback_suggestions(query, recommendations, preferences)
        suggestions = await _translate_suggestions(suggestions, output_language)
        return {
            "message": raw.strip(),
            "suggested_queries": suggestions,
        }


async def generate_concierge_message(
    query: str,
    recommendations: list[dict[str, Any]],
    output_language: str | None = None,
    preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate the assistant summary + follow-up suggestions.

    Returns ``{"message": str, "suggested_queries": list[str]}``.
    """
    settings = get_ai_settings()
    provider = (settings.llm_provider or "auto").lower()
    prompt = build_concierge_prompt(query, recommendations, output_language=output_language)

    if provider == "none":
        return await _make_fallback_result(query, recommendations, preferences, output_language)

    if provider in ("cloud", "auto"):
        try:
            content = await call_cloud_llm(prompt)
            if content:
                result = await _extract_concierge_result(content, query, recommendations, preferences, output_language)
                if result:
                    return result
                return await _make_fallback_result(query, recommendations, preferences, output_language)
        except Exception:
            if provider == "cloud":
                return await _make_fallback_result(query, recommendations, preferences, output_language)

    if provider in ("local", "auto"):
        try:
            content = await call_local_llm(prompt)
            if content:
                result = await _extract_concierge_result(content, query, recommendations, preferences, output_language)
                if result:
                    return result
                return await _make_fallback_result(query, recommendations, preferences, output_language)
        except Exception:
            if provider == "local":
                return await _make_fallback_result(query, recommendations, preferences, output_language)

    return await _make_fallback_result(query, recommendations, preferences, output_language)
