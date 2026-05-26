"""
Trancendos Sentinel Station Configuration
===========================================
Configuration for the Sentinel Station event distribution hub.

The Sentinel Station serves as the interplexus hub for cross-gateway
event distribution using Redis Pub/Sub. It defines channels, retry
strategies, and failover behavior.

Features:
    - Sentinel channel configuration with retry policies
    - Redis connection settings with health checks
    - Graceful fallback configuration for when Redis is unavailable
    - Event serialization and compression settings
    - Circuit breaker configuration for Redis connections
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from shared_core.infinity.nomenclature import SentinelChannel


# ── Redis Connection Configuration ──────────────────────────────────────────


@dataclass(frozen=True)
class RedisConfig:
    """Redis connection configuration for Sentinel Station.

    All values can be overridden via environment variables.
    """

    host: str = os.getenv("REDIS_HOST", "localhost")
    port: int = int(os.getenv("REDIS_PORT", "6379"))
    password: Optional[str] = os.getenv("REDIS_PASSWORD", None)
    db: int = int(os.getenv("REDIS_DB", "0"))
    ssl: bool = os.getenv("REDIS_SSL", "false").lower() in ("true", "1", "yes")
    socket_timeout: float = float(os.getenv("REDIS_SOCKET_TIMEOUT", "5.0"))
    socket_connect_timeout: float = float(os.getenv("REDIS_CONNECT_TIMEOUT", "3.0"))
    max_connections: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "10"))
    health_check_interval: int = int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30"))

    @property
    def url(self) -> str:
        """Build Redis URL from configuration."""
        scheme = "rediss" if self.ssl else "redis"
        auth = f":{self.password}@" if self.password else ""
        return f"{scheme}://{auth}{self.host}:{self.port}/{self.db}"


# ── Retry and Failover Configuration ────────────────────────────────────────


@dataclass(frozen=True)
class RetryConfig:
    """Retry configuration for Sentinel Station operations."""

    max_retries: int = int(os.getenv("SENTINEL_MAX_RETRIES", "3"))
    retry_delay_base: float = float(os.getenv("SENTINEL_RETRY_DELAY_BASE", "1.0"))
    retry_delay_max: float = float(os.getenv("SENTINEL_RETRY_DELAY_MAX", "30.0"))
    retry_backoff_factor: float = float(os.getenv("SENTINEL_RETRY_BACKOFF", "2.0"))
    circuit_breaker_threshold: int = int(os.getenv("SENTINEL_CB_THRESHOLD", "5"))
    circuit_breaker_reset_timeout: float = float(os.getenv("SENTINEL_CB_RESET_TIMEOUT", "60.0"))


# ── Channel Configuration ───────────────────────────────────────────────────


@dataclass
class ChannelConfig:
    """Configuration for a single Sentinel channel."""

    name: str
    description: str = ""
    max_message_size: int = 1024 * 1024  # 1MB
    batch_size: int = 100
    batch_interval: float = 0.1  # seconds
    persistent: bool = True
    retry_on_failure: bool = True


# ── Fallback Configuration ──────────────────────────────────────────────────


@dataclass(frozen=True)
class FallbackConfig:
    """Configuration for in-process fallback when Redis is unavailable.

    When Redis is down, Sentinel Station falls back to an in-process
    async pub/sub system that mirrors the Redis Pub/Sub interface.
    Events are distributed locally within the gateway process.

    This ensures the system remains functional even without Redis,
    though cross-gateway distribution is unavailable.
    """

    enabled: bool = os.getenv("SENTINEL_FALLBACK_ENABLED", "true").lower() in ("true", "1", "yes")
    max_queue_size: int = int(os.getenv("SENTINEL_FALLBACK_QUEUE_SIZE", "10000"))
    max_subscribers_per_channel: int = int(os.getenv("SENTINEL_FALLBACK_MAX_SUBS", "100"))


# ── Sentinel Station Configuration (Composite) ──────────────────────────────


@dataclass
class SentinelStationConfig:
    """Complete Sentinel Station configuration.

    Aggregates Redis, retry, channel, and fallback configurations
    into a single configuration object.
    """

    redis: RedisConfig = field(default_factory=RedisConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    fallback: FallbackConfig = field(default_factory=FallbackConfig)
    service_name: str = os.getenv("SENTINEL_SERVICE_NAME", "sentinel-station")
    service_port: int = int(os.getenv("SENTINEL_PORT", "8041"))
    event_ttl: int = int(os.getenv("SENTINEL_EVENT_TTL", "86400"))  # 24 hours
    compression_threshold: int = int(os.getenv("SENTINEL_COMPRESSION_THRESHOLD", "1024"))
    redis_channel_prefix: str = "sentinel:"

    # Pre-configured channels based on nomenclature
    channels: dict[str, ChannelConfig] = field(
        default_factory=lambda: {
            SentinelChannel.PLATFORM.value: ChannelConfig(
                name=SentinelChannel.PLATFORM.value,
                description="Platform-level events: topology changes, system alerts",
            ),
            SentinelChannel.AGENTS.value: ChannelConfig(
                name=SentinelChannel.AGENTS.value,
                description="Agent lifecycle events: creation, deletion, status changes",
            ),
            SentinelChannel.MODELS.value: ChannelConfig(
                name=SentinelChannel.MODELS.value,
                description="Model events: registration, routing changes",
            ),
            SentinelChannel.WORKFLOWS.value: ChannelConfig(
                name=SentinelChannel.WORKFLOWS.value,
                description="Workflow events: creation, execution, completion",
            ),
            SentinelChannel.SECURITY.value: ChannelConfig(
                name=SentinelChannel.SECURITY.value,
                description="Security events: vault access, audit entries, threat detection",
            ),
            SentinelChannel.HIVE.value: ChannelConfig(
                name=SentinelChannel.HIVE.value,
                description="Data transfer events through The HIVE",
            ),
            SentinelChannel.NEXUS.value: ChannelConfig(
                name=SentinelChannel.NEXUS.value,
                description="AI/Agent/Bot movement events through The Nexus",
            ),
            SentinelChannel.BRIDGE.value: ChannelConfig(
                name=SentinelChannel.BRIDGE.value,
                description="User transfer events across the Infinity Bridge",
            ),
            SentinelChannel.PILLARS.value: ChannelConfig(
                name=SentinelChannel.PILLARS.value,
                description="Prime status and pillar health events",
            ),
            SentinelChannel.INFRASTRUCTURE.value: ChannelConfig(
                name=SentinelChannel.INFRASTRUCTURE.value,
                description="Infrastructure health, node topology, and scaling events",
            ),
            SentinelChannel.EVENTS.value: ChannelConfig(
                name=SentinelChannel.EVENTS.value,
                description="General platform events and notifications",
            ),
        }
    )


# Singleton configuration instance
sentinel_config = SentinelStationConfig()
