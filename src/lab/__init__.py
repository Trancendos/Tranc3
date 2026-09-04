"""The Lab — language and skill capability registry."""

from src.lab.languages import (
    LANGUAGES,
    Language,
    Tool,
    Verification,
    language,
    resolve_language,
    skills_matrix,
    verification_for,
)

__all__ = [
    "LANGUAGES",
    "Language",
    "Tool",
    "Verification",
    "language",
    "resolve_language",
    "skills_matrix",
    "verification_for",
]
