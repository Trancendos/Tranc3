"""
Event Bus Types — Data models and configuration
=================================================
Ported from @trancendos/event-bus TypeScript types.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Callable, Coroutine, Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────


class PlatformEventType(str, enum.Enum):
    """Well-known platform event types."""
    # User events
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"

    # Auth events
    AUTH_TOKEN_ISSUED = "auth.token.issued"
    AUTH_TOKEN_REVOKED = "auth.token.revoked"
    AUTH_MFA_CHALLENGE = "auth.mfa.challenge"
    AUTH_MFA_VERIFIED = "auth.mfa.verified"

    # AI events
    AI_INFERENCE_REQUEST = "ai.inference.request"
    AI_INFERENCE_COMPLETE = "ai.inference.complete"
    AI_INFERENCE_FAILED = "ai.inference.failed"
    AI_MODEL_LOADED = "ai.model.loaded"

    # Service events
    SERVICE_REGISTERED = "service.registered"
    SERVICE_HEALTH_CHANGED = "service.health.changed"
    SERVICE_CIRCUIT_OPENED = "service.circuit.opened"
    SERVICE_CIRCUIT_CLOSED = "service.circuit.closed"

    # Workflow events
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_STEP_COMPLETE = "workflow.step.complete"

    # Financial events
    ORDER_CREATED = "order.created"
    ORDER_COMPLETED = "order.completed"
    PAYMENT_RECEIVED = "payment.received"
    PAYMENT_FAILED = "payment.failed"

    # Secret events
    SECRET_STORED = "secret.stored"
    SECRET_RETRIEVED = "secret.retrieved"
    SECRET_ROTATED = "secret.rotated"
    SECRET_DELETED = "secret.deleted"

    # Notification events
    NOTIFICATION_SENT = "notification.sent"
    NOTIFICATION_READ = "notification.read"


class DeliveryStatus(str, enum.Enum):
    """Event delivery status."""
    DELIVERED = "delivered"
    PENDING = "pending"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


# ── Type Aliases ─────────────────────────────────────────────

EventCallback = Callable[..., Coroutine[Any, Any, Any]]


# ── Data Models ──────────────────────────────────────────────


class EventMetadata(BaseModel):
    """Metadata attached to every event."""
    event_id: str
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    source: str = ""
    tenant_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


class EventEnvelope(BaseModel):
    """Complete event envelope with metadata and payload."""
    event_type: str
    data: dict[str, Any] = Field(default_factory=dict)
    metadata: EventMetadata


class EventFilter(BaseModel):
    """Filter for event subscriptions."""
    tenant_id: Optional[str] = None
    source: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    min_version: Optional[str] = None


class EventSubscription(BaseModel):
    """A subscription for event delivery."""
    id: str
    subscriber: str
    event_pattern: str
    delivery_type: str = "callback"  # callback, webhook, queue
    endpoint: Optional[str] = None
    filter: Optional[EventFilter] = None
    enabled: bool = True
    max_retries: int = 3
    retry_delay_ms: int = 1000
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DeliveryResult(BaseModel):
    """Result of delivering an event to a subscriber."""
    subscription_id: str
    status: DeliveryStatus = DeliveryStatus.PENDING
    error: Optional[str] = None
    attempts: int = 0
    latency_ms: float = 0.0


class EventBusConfig(BaseModel):
    """Event bus configuration."""
    persist_events: bool = False
    max_payload_size: int = 1048576  # 1MB
    batch_size: int = 100
    batch_flush_interval_ms: int = 5000
    default_max_retries: int = 3
    default_retry_delay_ms: int = 1000
    sqlite_path: Optional[str] = None  # Set to enable SQLite persistence

    model_config = {"frozen": True}


# ── Defaults ─────────────────────────────────────────────────

DEFAULT_EVENT_BUS_CONFIG = EventBusConfig()
