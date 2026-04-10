"""
Prompt templates and helpers for LLM calls.

This module centralizes all instruction text sent to LLMs so they can be
edited, versioned, and tested separately from the call/validation logic.

Best practices implemented here:
- Keep instruction text in one place, with clear comments.
- Use a deterministic JSON schema in the prompt to reduce hallucination.
- Include an explicit example of the expected JSON shape.
"""
from __future__ import annotations

import json
from typing import Any, List


CONCIERGE_PROMPT_TEMPLATE = (
    "You are a hotel booking concierge. Return ONLY a JSON object with three keys:\n"
    "- summary: a concise, friendly recommendation summary in plain text (2-4 sentences). "
    "Do NOT use markdown, code fences, or any formatting inside the summary value.\n"
    "- top_recommendation: an object with title, city, country, price_per_night.\n"
    "- suggested_queries: an array of exactly 3 short follow-up questions the user might want to ask next. "
    "Each suggestion must be a natural sentence (not a keyword). Make them contextually relevant: "
    "e.g. explore other cities, adjust budget, ask about amenities, or widen the search.\n"
    "Do NOT invent any fields or prices; the top_recommendation MUST come from the supplied recommendations.\n"
    "Return ONLY the raw JSON object. Do NOT wrap it in markdown code fences (``` or ```json). "
    "Do NOT add any text before or after the JSON.\n"
    "Here is an example of the exact JSON shape expected:\n"
    "{\n  \"summary\": \"Short friendly text...\",\n  \"top_recommendation\": {\n    \"title\": \"Suite with Sea View\",\n    \"city\": \"Lisbon\",\n    \"country\": \"Portugal\",\n    \"price_per_night\": 120.0\n  },\n  \"suggested_queries\": [\n    \"Show me cheaper options in other cities\",\n    \"Any rooms with a workspace?\",\n    \"What about hotels in Barcelona?\"\n  ]\n}\n"
)


def build_concierge_prompt(query: str, recommendations: List[dict[str, Any]], output_language: str | None = None) -> str:
    """Return the full prompt string for the concierge LLM.

    The function inserts the query and a JSON-encoded list of recommendation
    metadata. Keeping the template here makes it easy to adjust instructions
    (tone, required fields, examples) without touching the LLM invocation
    and validation logic.
    """
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

    prompt = CONCIERGE_PROMPT_TEMPLATE + "\nUser query: " + query + "\nRecommendations JSON: " + json.dumps(
        safe_recommendations, ensure_ascii=True
    )

    if output_language:
        prompt += (
            "\nIMPORTANT: The user's language is '" + output_language + "'. "
            "Write the 'summary' field in that language. "
            "Write every string in the 'suggested_queries' array in that language too. "
            "Translate city and country names in the JSON to that language as well."
        )

    return prompt
