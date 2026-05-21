"""
AI Provider Base Class
=======================
Abstract base for all AI providers.
"""

from __future__ import annotations

import abc
from typing import Any

from src.ai_gateway.types import AIRequest, AIResponse, ProviderHealth


class AIProvider(abc.ABC):
    """Base class for AI providers."""

    def __init__(self, name: str, base_url: str = "", api_key: str = "") -> None:
        self.name = name
        self.base_url = base_url
        self.api_key = api_key

    @abc.abstractmethod
    async def complete(self, request: AIRequest) -> AIResponse:
        """Generate a completion for the given request."""
        ...

    @abc.abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Check provider health."""
        ...

    @abc.abstractmethod
    def get_models(self) -> list[str]:
        """List available models."""
        ...
