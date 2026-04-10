from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class AISettings:
    """Runtime configuration for AI features.

    All LLM selection stays internal to the application. The public API should
    not expose model/provider switches to end users.
    """

    chroma_collection: str = "rooms_catalog"
    chroma_path: Path = Path(__file__).resolve().parent.parent / "chroma_store"
    # Default to "none" so the app works out of the box without any LLM runtime.
    # Valid values: none, auto, local, cloud
    llm_provider: str = os.getenv("CONCIERGE_LLM_PROVIDER", "none")
    llm_model: str | None = os.getenv("CONCIERGE_LLM_MODEL")
    local_llm_base_url: str = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434")
    local_llm_model: str = os.getenv("LOCAL_LLM_MODEL", "deepseek-r1:8b")
    cloud_llm_base_url: str = os.getenv("CLOUD_LLM_BASE_URL", "https://api.openai.com/v1")
    cloud_llm_model: str = os.getenv("CLOUD_LLM_MODEL", "gpt-4o-mini")
    cloud_llm_api_key: str | None = os.getenv("CLOUD_LLM_API_KEY")
    local_llm_timeout_seconds: float = float(os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", "8"))
    cloud_llm_timeout_seconds: float = float(os.getenv("CLOUD_LLM_TIMEOUT_SECONDS", "10"))
    # Premium i18n: when True, LLM-translated responses match the user's
    # query language (cards, message, suggestions).  When False (default),
    # only language detection + English translation runs (needed for search),
    # but output stays in the original DB / English language.
    premium_i18n: bool = os.getenv("CONCIERGE_PREMIUM_I18N", "false").lower() in ("1", "true", "yes")


def get_ai_settings() -> AISettings:
    """Return a fresh settings object so env changes are visible after reload."""
    return AISettings()
