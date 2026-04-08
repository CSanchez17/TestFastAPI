from __future__ import annotations

import json
from typing import Any

import httpx

from .config import get_ai_settings


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


def build_concierge_prompt(query: str, recommendations: list[dict[str, Any]]) -> str:
    """Build a compact prompt for whichever LLM backend is active."""
    safe_recommendations = [
        {
            "title": item.get("title"),
            "price_per_night": item.get("price_per_night"),
            "city": item.get("city"),
            "country": item.get("country"),
            "reason": item.get("reason"),
        }
        for item in recommendations
    ]
    return (
        "You are a hotel booking concierge. "
        "Write a concise, friendly recommendation summary in 2-4 sentences. "
        "Mention budget fit and why the top option matches. "
        "Do not invent fields.\n"
        f"User query: {query}\n"
        f"Recommendations JSON: {json.dumps(safe_recommendations, ensure_ascii=True)}"
    )


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


async def generate_concierge_message(query: str, recommendations: list[dict[str, Any]]) -> str:
    """Generate the assistant summary using internal provider selection only."""
    settings = get_ai_settings()
    provider = (settings.llm_provider or "auto").lower()
    prompt = build_concierge_prompt(query, recommendations)

    if provider == "none":
        return build_fallback_message(query, recommendations)

    if provider in ("cloud", "auto"):
        try:
            content = await call_cloud_llm(prompt)
            if content:
                return content
        except Exception:
            if provider == "cloud":
                return build_fallback_message(query, recommendations)

    if provider in ("local", "auto"):
        try:
            content = await call_local_llm(prompt)
            if content:
                return content
        except Exception:
            if provider == "local":
                return build_fallback_message(query, recommendations)

    return build_fallback_message(query, recommendations)
