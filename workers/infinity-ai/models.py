"""
Pydantic models for the infinity-ai worker.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from config import DEFAULT_DAILY_TOKEN_LIMIT


class ProviderName(str, Enum):
    ollama = "ollama"
    groq = "groq"
    cerebras = "cerebras"
    openrouter = "openrouter"
    huggingface = "huggingface"
    together = "together"
    deepseek = "deepseek"
    offline = "offline"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "llama3.2"
    messages: List[ChatMessage]
    max_tokens: int = 1024
    temperature: float = 0.7
    stream: bool = False
    tenant_id: Optional[str] = None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: List[ChatCompletionChoice] = Field(default_factory=list)
    usage: ChatCompletionUsage = Field(default_factory=ChatCompletionUsage)
    provider: str = ""  # Which provider served the request


class TokenBudget(BaseModel):
    tenant_id: str
    daily_limit: int = DEFAULT_DAILY_TOKEN_LIMIT
    used_today: int = 0
    last_reset: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
