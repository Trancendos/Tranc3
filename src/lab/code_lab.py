# src/lab/code_lab.py
# The Lab — AI-powered code creation platform for Trancendos.
#
# The Lab provides:
#   - Code generation sessions (language-agnostic)
#   - Project scaffold generation
#   - Code review and explanation
#   - Integration with The Spark (MCP tools) for tool-augmented generation
#   - Session persistence (in-memory; backed by vector store when available)
#
# Foundation: Claude Code-style agentic coding environment.

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class LabSessionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETE = "complete"
    ARCHIVED = "archived"


class TaskType(str, Enum):
    GENERATE = "generate"  # New code from description
    REFACTOR = "refactor"  # Improve existing code
    REVIEW = "review"  # Explain / audit code
    DEBUG = "debug"  # Identify and fix issues
    SCAFFOLD = "scaffold"  # New project structure
    TEST = "test"  # Generate test suite


@dataclass
class LabMessage:
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LabSession:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: LabSessionStatus = LabSessionStatus.ACTIVE
    language: str = "python"
    task_type: TaskType = TaskType.GENERATE
    messages: List[LabMessage] = field(default_factory=list)
    context_files: Dict[str, str] = field(default_factory=dict)  # filename → content
    generated_artifacts: Dict[str, str] = field(default_factory=dict)

    def add_message(self, role: str, content: str, **metadata) -> LabMessage:
        msg = LabMessage(role=role, content=content, metadata=metadata)
        self.messages.append(msg)
        self.updated_at = time.time()
        return msg

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "status": self.status.value,
            "language": self.language,
            "task_type": self.task_type.value,
            "message_count": len(self.messages),
            "artifact_count": len(self.generated_artifacts),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TheLab:
    """
    The Lab — AI code creation platform.

    Each session maintains full conversation context for multi-turn coding tasks.
    Generation delegates to the active inference tier (Tranc3Engine → Ollama →
    OpenRouter → stub) via the Spark MCP or direct engine call.
    """

    def __init__(self):
        self._sessions: Dict[str, LabSession] = {}

    def create_session(
        self,
        user_id: Optional[str] = None,
        language: str = "python",
        task_type: TaskType = TaskType.GENERATE,
    ) -> LabSession:
        session = LabSession(user_id=user_id, language=language, task_type=task_type)
        self._sessions[session.id] = session
        self._emit("lab.session.created", {"session_id": session.id, "language": language})
        logger.info(
            "lab: session created id=%s lang=%s task=%s",
            sanitize_for_log(session.id),
            sanitize_for_log(language),
            sanitize_for_log(task_type.value),
        )  # codeql[py/cleartext-logging]
        return session

    def get_session(self, session_id: str) -> Optional[LabSession]:
        return self._sessions.get(session_id)

    def list_sessions(self, user_id: Optional[str] = None) -> List[LabSession]:
        sessions = list(self._sessions.values())
        if user_id:
            sessions = [s for s in sessions if s.user_id == user_id]
        return sorted(sessions, key=lambda s: s.updated_at, reverse=True)[:100]

    def send_message(
        self,
        session_id: str,
        content: str,
        role: str = "user",
    ) -> Optional[LabMessage]:
        session = self._sessions.get(session_id)
        if not session or session.status != LabSessionStatus.ACTIVE:
            return None
        msg = session.add_message(role=role, content=content)
        return msg

    def add_context_file(
        self,
        session_id: str,
        filename: str,
        content: str,
    ) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.context_files[filename] = content
        session.updated_at = time.time()
        return True

    def save_artifact(
        self,
        session_id: str,
        filename: str,
        content: str,
    ) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.generated_artifacts[filename] = content
        session.updated_at = time.time()
        self._emit("lab.artifact.saved", {"session_id": session_id, "filename": filename})
        return True

    def close_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.status = LabSessionStatus.COMPLETE
        session.updated_at = time.time()
        return True

    def delete_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def stats(self) -> Dict[str, Any]:
        statuses: Dict[str, int] = {}
        for s in self._sessions.values():
            statuses[s.status.value] = statuses.get(s.status.value, 0) + 1
        return {
            "service": "the-lab",
            "total_sessions": len(self._sessions),
            "by_status": statuses,
        }

    def _emit(self, event_type: str, metadata: Optional[Dict] = None) -> None:
        try:
            from src.observability.observatory import EventCategory, observe

            observe(
                event_type, category=EventCategory.DATA, service="the-lab", metadata=metadata or {}
            )
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream


_lab: Optional[TheLab] = None


def get_lab() -> TheLab:
    global _lab
    if _lab is None:
        _lab = TheLab()
    return _lab
