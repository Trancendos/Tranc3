"""The Lab — Pydantic models"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CodeBackend(str, Enum):
    ollama_deepseek = "ollama_deepseek"
    ollama_codellama = "ollama_codellama"
    ollama_qwen = "ollama_qwen"
    tabby = "tabby"
    huggingface = "huggingface"
    openrouter = "openrouter"
    offline = "offline"


class TaskType(str, Enum):
    complete = "complete"
    generate = "generate"
    review = "review"
    explain = "explain"
    refactor = "refactor"
    test = "test"
    fix = "fix"


class CodeRequest(BaseModel):
    prompt: str
    language: Optional[str] = None
    context: Optional[str] = None
    task_type: TaskType = TaskType.generate
    max_tokens: int = Field(default=2048, ge=64, le=8192)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CodeResponse(BaseModel):
    request_id: str
    result: str
    language: Optional[str]
    task_type: TaskType
    backend: CodeBackend
    tokens_used: Optional[int] = None
    latency_ms: Optional[float] = None
    created_at: Optional[str] = None


class BackendStatus(BaseModel):
    name: CodeBackend
    healthy: bool
    pheromone: float
    calls_in_window: int
    quota_remaining: int
    model: Optional[str] = None


class LabStatus(BaseModel):
    active_backend: CodeBackend
    backends: List[BackendStatus]
    openai_compat_url: str
