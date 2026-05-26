"""
AeonMind Bot Services — Tier 5 Stateless Service Workers.

Bot Services are the lowest-tier entities in the Tranc3 hierarchy.
They perform single-purpose, stateless operations and cannot act
autonomously — they are invoked by Agents (Tier 4) or AI Complexes
(Tier 3).

Custom Hierarchy:
  AI    = The overarching ML/LLM Complex (Tier 3)
  Agent = Lower-level autonomous AI (Tier 4)
  Bot   = Stateless service worker/function (Tier 5)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class BotCapability(Enum):
    """Capabilities that a bot service worker can provide."""
    TRANSLATE = "translate"
    SUMMARIZE = "summarize"
    CLASSIFY = "classify"
    EXTRACT = "extract"
    VALIDATE = "validate"
    TRANSFORM = "transform"
    MONITOR = "monitor"
    NOTIFY = "notify"
    LOG = "log"
    CACHE = "cache"
    ROUTE = "route"
    FILTER = "filter"
    ENRICH = "enrich"
    EMBED = "embed"
    GENERIC = "generic"


class BotStatus(Enum):
    """Status of a bot service worker."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class BotExecutionResult:
    """Result of a bot execution."""
    bot_id: str
    capability: str
    status: BotStatus
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BotServiceConfig:
    """Configuration for a bot service worker."""
    name: str = "unnamed-bot"
    capability: BotCapability = BotCapability.GENERIC
    stateless: bool = True
    timeout: float = 30.0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)


class BotServiceWorker:
    """Tier 5 — Stateless Bot Service Worker.

    Performs single-purpose, stateless operations. Cannot act
    autonomously — must be invoked by Agents or AI Complexes.
    """

    def __init__(self, config: Optional[BotServiceConfig] = None):
        self.config = config or BotServiceConfig()
        self.id = f"bot-{uuid.uuid4().hex[:8]}"
        self.status = BotStatus.IDLE
        self._execution_count = 0
        self._success_count = 0
        self._total_execution_time = 0.0

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def capability(self) -> BotCapability:
        return self.config.capability

    def execute(self, payload: Dict[str, Any]) -> BotExecutionResult:
        """Execute the bot's service function.

        Args:
            payload: Input data for the bot operation.

        Returns:
            BotExecutionResult with status, output, and timing.
        """
        start_time = time.time()
        self.status = BotStatus.RUNNING

        try:
            output = self._process(payload)
            execution_time = time.time() - start_time

            self._execution_count += 1
            self._success_count += 1
            self._total_execution_time += execution_time
            self.status = BotStatus.COMPLETED

            return BotExecutionResult(
                bot_id=self.id,
                capability=self.config.capability.value,
                status=BotStatus.COMPLETED,
                success=True,
                output=output,
                execution_time=execution_time,
            )

        except Exception as e:
            execution_time = time.time() - start_time
            self._execution_count += 1
            self.status = BotStatus.FAILED

            return BotExecutionResult(
                bot_id=self.id,
                capability=self.config.capability.value,
                status=BotStatus.FAILED,
                success=False,
                error=str(e),
                execution_time=execution_time,
            )

    def _process(self, payload: Dict[str, Any]) -> Any:
        """Process the payload based on capability.

        Override this method in specialized bot implementations.
        """
        capability = self.config.capability

        if capability == BotCapability.TRANSLATE:
            return {"translated": payload.get("text", ""), "lang": payload.get("target_lang", "en")}
        elif capability == BotCapability.SUMMARIZE:
            text = payload.get("text", "")
            return {"summary": text[:100] + "..." if len(text) > 100 else text}
        elif capability == BotCapability.MONITOR:
            return {"status": "healthy", "timestamp": time.time()}
        elif capability == BotCapability.VALIDATE:
            return {"valid": True, "checked": payload}
        elif capability == BotCapability.LOG:
            return {"logged": True, "entry_id": str(uuid.uuid4().hex[:8])}
        elif capability == BotCapability.CACHE:
            return {"cached": True, "key": payload.get("key", "default")}
        elif capability == BotCapability.NOTIFY:
            return {"notified": True, "recipient": payload.get("recipient", "all")}
        else:
            return {"processed": payload}

    @property
    def success_rate(self) -> float:
        """Get the success rate of this bot."""
        if self._execution_count == 0:
            return 0.0
        return self._success_count / self._execution_count

    @property
    def avg_execution_time(self) -> float:
        """Get average execution time."""
        if self._execution_count == 0:
            return 0.0
        return self._total_execution_time / self._execution_count

    def summary(self) -> Dict[str, Any]:
        """Get a summary of this bot's state."""
        return {
            "id": self.id,
            "name": self.config.name,
            "capability": self.config.capability.value,
            "status": self.status.value,
            "tier": "BOT (Tier 5)",
            "stateless": self.config.stateless,
            "execution_count": self._execution_count,
            "success_rate": round(self.success_rate, 4),
            "avg_execution_time": round(self.avg_execution_time, 4),
        }


class BotServiceRegistry:
    """Centralized registry for managing bot service workers."""

    def __init__(self):
        self._bots: Dict[str, BotServiceWorker] = {}

    def register(self, bot_id: str, bot: BotServiceWorker) -> None:
        """Register a bot service worker."""
        self._bots[bot_id] = bot

    def unregister(self, bot_id: str) -> None:
        """Unregister a bot service worker."""
        self._bots.pop(bot_id, None)

    def get(self, bot_id: str) -> Optional[BotServiceWorker]:
        """Get a bot by ID."""
        return self._bots.get(bot_id)

    def list_all(self) -> List[str]:
        """List all registered bot IDs."""
        return list(self._bots.keys())

    def list_by_capability(self, capability: BotCapability) -> List[BotServiceWorker]:
        """List all bots with a specific capability."""
        return [bot for bot in self._bots.values() if bot.capability == capability]

    def __len__(self) -> int:
        return len(self._bots)

    def execute(self, bot_id: str, payload: Dict[str, Any]) -> BotExecutionResult:
        """Execute a specific bot by ID."""
        bot = self._bots.get(bot_id)
        if bot is None:
            return BotExecutionResult(
                bot_id=bot_id,
                capability="unknown",
                status=BotStatus.FAILED,
                success=False,
                error=f"Bot {bot_id} not found",
            )
        return bot.execute(payload)
