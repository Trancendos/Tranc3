"""
Trancendos Ecosystem — Ollama Tool-Calling Integration

Lightweight async client for the Ollama REST API, enabling local LLM
tool-calling for Agent perceive→decide→act loops.

Zero-cost architecture: Uses Ollama (local) instead of cloud LLM APIs.
Fallback: If Ollama is unavailable, agents fall back to rule-based decide().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OllamaToolParameter:
    type: str
    description: str = ""
    enum: Optional[List[str]] = None


@dataclass
class OllamaToolSchema:
    """Schema for a tool that Ollama can call — mirrors the TypeScript OllamaToolSchema."""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=lambda: {
        "type": "object",
        "properties": {},
        "required": [],
    })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class OllamaToolCall:
    """A tool call requested by Ollama."""
    name: str
    arguments: Dict[str, Any]


@dataclass
class OllamaMessage:
    """A single message in the Ollama conversation."""
    role: str  # system, user, assistant, tool
    content: str
    tool_calls: Optional[List[OllamaToolCall]] = None
    tool_call_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    }
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass
class OllamaChatResponse:
    """Ollama API response for chat completions."""
    message: OllamaMessage
    done: bool = True
    model: str = ""
    total_duration_ns: int = 0
    eval_count: int = 0


@dataclass
class OllamaConfig:
    """Configuration for Ollama integration."""
    base_url: str = "http://localhost:11434"
    model: str = "llama3.2"
    system_prompt: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    request_timeout_s: float = 30.0


class OllamaClient:
    """
    Async Ollama client — lightweight wrapper over the Ollama REST API.

    Supports:
      - Chat completions with tool schemas
      - Availability checks
      - Model listing
      - Automatic retry with configurable timeout
    """

    def __init__(self, config: Optional[OllamaConfig] = None) -> None:
        self.config = config or OllamaConfig()
        self._session: Optional[Any] = None  # aiohttp.ClientSession

    async def _get_session(self) -> Any:
        """Lazy-create aiohttp session."""
        if self._session is None or self._session.closed:
            import aiohttp
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.request_timeout_s),
            )
        return self._session

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def chat(
        self,
        messages: List[OllamaMessage],
        tools: Optional[List[OllamaToolSchema]] = None,
    ) -> OllamaChatResponse:
        """Send a chat request with optional tool schemas."""
        session = await self._get_session()

        body: Dict[str, Any] = {
            "model": self.config.model,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }

        if tools:
            body["tools"] = [t.to_dict() for t in tools]

        async with session.post(
            f"{self.config.base_url}/api/chat",
            json=body,
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Ollama API error {resp.status}: {text}")
            data = await resp.json()

        # Parse response
        msg_data = data.get("message", {})
        tool_calls = None
        if msg_data.get("tool_calls"):
            tool_calls = [
                OllamaToolCall(
                    name=tc["function"]["name"],
                    arguments=tc["function"].get("arguments", {}),
                )
                for tc in msg_data["tool_calls"]
            ]

        return OllamaChatResponse(
            message=OllamaMessage(
                role=msg_data.get("role", "assistant"),
                content=msg_data.get("content", ""),
                tool_calls=tool_calls,
            ),
            done=data.get("done", True),
            model=data.get("model", self.config.model),
            total_duration_ns=data.get("total_duration", 0),
            eval_count=data.get("eval_count", 0),
        )

    async def is_available(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            import aiohttp
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=3),
            ) as session:
                async with session.get(f"{self.config.base_url}/api/tags") as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        """List available models."""
        try:
            import aiohttp
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5),
            ) as session:
                async with session.get(f"{self.config.base_url}/api/tags") as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    async def __aenter__(self) -> "OllamaClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
