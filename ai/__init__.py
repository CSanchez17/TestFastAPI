"""AI package entrypoints for recommendation and generation features.

This package keeps AI concerns isolated from the HTTP layer so additional
AI use cases can be added without coupling them to FastAPI routes.
"""

from .service import recommend_rooms

__all__ = ["recommend_rooms"]
