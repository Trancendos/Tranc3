"""
Worker Database Registry — canonical list of every SQLite database across all
self-hosted workers, with backup tier classification and RTO/RPO targets.

Tiers
-----
CRITICAL  RTO ≤ 1 h  / RPO ≤ 15 min — auth, vault, users, payments, ledger
HIGH      RTO ≤ 4 h  / RPO ≤ 1 h   — audit, orders, notifications, identity
STANDARD  RTO ≤ 24 h / RPO ≤ 6 h   — most operational workers
LOW       RTO ≤ 72 h / RPO ≤ 24 h  — analytics, cache, rate-limiting, CDN
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class BackupTier(Enum):
    CRITICAL = "critical"  # backup every 15 min
    HIGH = "high"  # backup every 1 h
    STANDARD = "standard"  # backup every 6 h
    LOW = "low"  # backup every 24 h


# Retention policy: (daily_count, weekly_count, monthly_count)
RETENTION: dict[BackupTier, tuple[int, int, int]] = {
    BackupTier.CRITICAL: (7, 4, 6),
    BackupTier.HIGH: (7, 4, 3),
    BackupTier.STANDARD: (7, 4, 2),
    BackupTier.LOW: (3, 2, 1),
}

# RTO / RPO targets in minutes
RTO_MINUTES: dict[BackupTier, int] = {
    BackupTier.CRITICAL: 60,
    BackupTier.HIGH: 240,
    BackupTier.STANDARD: 1440,
    BackupTier.LOW: 4320,
}

RPO_MINUTES: dict[BackupTier, int] = {
    BackupTier.CRITICAL: 15,
    BackupTier.HIGH: 60,
    BackupTier.STANDARD: 360,
    BackupTier.LOW: 1440,
}


@dataclass
class WorkerDB:
    """Descriptor for a single worker's SQLite database."""

    worker: str  # canonical worker name
    env_var: str  # env var for the database path
    default_path: str  # default path when env var not set
    tier: BackupTier
    description: str = ""
    extra_paths: List[str] = field(default_factory=list)  # additional DB files

    @property
    def resolved_path(self) -> str:
        return os.environ.get(self.env_var, self.default_path)

    @property
    def backup_interval_minutes(self) -> int:
        return RPO_MINUTES[self.tier]

    @property
    def rto_minutes(self) -> int:
        return RTO_MINUTES[self.tier]

    @property
    def rpO_minutes(self) -> int:
        return RPO_MINUTES[self.tier]


WORKER_DATABASE_REGISTRY: List[WorkerDB] = [
    # ── CRITICAL ────────────────────────────────────────────────────────────────
    WorkerDB(
        worker="infinity-auth",
        env_var="AUTH_DATABASE_PATH",
        default_path="/data/auth.db",
        tier=BackupTier.CRITICAL,
        description="OAuth2 sessions, user credentials, refresh tokens",
    ),
    WorkerDB(
        worker="vault-service",
        env_var="VAULT_DB_PATH",
        default_path="data/vault.db",
        tier=BackupTier.CRITICAL,
        description="AES-GCM encrypted platform secrets (The Void)",
    ),
    WorkerDB(
        worker="users-service",
        env_var="USERS_DATABASE_PATH",
        default_path="/data/users.db",
        tier=BackupTier.CRITICAL,
        description="User profiles, roles, PII",
    ),
    WorkerDB(
        worker="payments-service",
        env_var="PAYMENTS_DB_PATH",
        default_path="data/payments.db",
        tier=BackupTier.CRITICAL,
        description="Payment transactions — Royal Bank of Arcadia",
    ),
    WorkerDB(
        worker="ledger-service",
        env_var="LEDGER_DB_PATH",
        default_path="data/ledger.db",
        tier=BackupTier.CRITICAL,
        description="Financial ledger — double-entry records",
    ),
    # ── HIGH ────────────────────────────────────────────────────────────────────
    WorkerDB(
        worker="audit-service",
        env_var="AUDIT_DB_PATH",
        default_path="data/audit.db",
        tier=BackupTier.HIGH,
        description="Compliance audit trail — The Observatory",
    ),
    WorkerDB(
        worker="orders-service",
        env_var="ORDERS_DB_PATH",
        default_path="data/orders.db",
        tier=BackupTier.HIGH,
        description="Order records — Arcadian Exchange",
    ),
    WorkerDB(
        worker="notifications",
        env_var="NOTIFICATIONS_DB_PATH",
        default_path="data/notifications.db",
        tier=BackupTier.HIGH,
        description="Notification queue and delivery log",
    ),
    WorkerDB(
        worker="identity-service",
        env_var="IDENTITY_DB_PATH",
        default_path="data/identities.db",
        tier=BackupTier.HIGH,
        description="Infinity-One identity profiles",
    ),
    WorkerDB(
        worker="infinity-one-service",
        env_var="INFINITY_ONE_DB_PATH",
        default_path="data/infinity_one.db",
        tier=BackupTier.HIGH,
        description="Single identity layer state",
    ),
    WorkerDB(
        worker="infinity-admin-service",
        env_var="INFINITY_ADMIN_DB_PATH",
        default_path="data/infinity_admin.db",
        tier=BackupTier.HIGH,
        description="Admin OS configuration and state",
    ),
    # ── STANDARD ────────────────────────────────────────────────────────────────
    WorkerDB(
        worker="the-grid",
        env_var="GRID_DB_PATH",
        default_path="data/grid.db",
        tier=BackupTier.STANDARD,
        description="Workflow DAG definitions and execution history",
    ),
    WorkerDB(
        worker="infinity-portal-service",
        env_var="INFINITY_PORTAL_DB_PATH",
        default_path="data/infinity_portal.db",
        tier=BackupTier.STANDARD,
        description="Portal login state and session routing",
    ),
    WorkerDB(
        worker="infinity-shards-service",
        env_var="INFINITY_SHARDS_DB_PATH",
        default_path="data/infinity_shards.db",
        tier=BackupTier.STANDARD,
        description="Entity power-up module state",
    ),
    WorkerDB(
        worker="config-service",
        env_var="CONFIG_DB_PATH",
        default_path="data/config.db",
        tier=BackupTier.STANDARD,
        description="Central platform configuration",
    ),
    WorkerDB(
        worker="queue-service",
        env_var="QUEUE_DB_PATH",
        default_path="data/queue.db",
        tier=BackupTier.STANDARD,
        description="The HIVE task queue state",
    ),
    WorkerDB(
        worker="sentinel-station-service",
        env_var="SENTINEL_DB_PATH",
        default_path="data/sentinel_station.db",
        tier=BackupTier.STANDARD,
        description="Active threat monitoring events",
    ),
    WorkerDB(
        worker="files-service",
        env_var="FILES_DB_PATH",
        default_path="data/files.db",
        tier=BackupTier.STANDARD,
        description="DocUtari file metadata",
    ),
    WorkerDB(
        worker="products-service",
        env_var="PRODUCTS_DB_PATH",
        default_path="data/products.db",
        tier=BackupTier.STANDARD,
        description="Product catalogue",
    ),
    WorkerDB(
        worker="search-service",
        env_var="SEARCH_DB_PATH",
        default_path="data/search.db",
        tier=BackupTier.STANDARD,
        description="Full-text search index",
    ),
    WorkerDB(
        worker="email-service",
        env_var="EMAIL_DB_PATH",
        default_path="data/email.db",
        tier=BackupTier.STANDARD,
        description="Email send queue and delivery log",
    ),
    WorkerDB(
        worker="cron-service",
        env_var="CRON_DB_PATH",
        default_path="data/cron.db",
        tier=BackupTier.STANDARD,
        description="Scheduled job definitions and run history",
    ),
    WorkerDB(
        worker="workflow-engine-service",
        env_var="WORKFLOW_DB_PATH",
        default_path="data/workflow_engine.db",
        tier=BackupTier.STANDARD,
        description="Digital Grid workflow engine state",
    ),
    WorkerDB(
        worker="monitoring",
        env_var="MONITORING_DB_PATH",
        default_path="data/monitoring.db",
        tier=BackupTier.STANDARD,
        description="Observatory metrics and alert history",
    ),
    WorkerDB(
        worker="infinity-ai",
        env_var="AI_GATEWAY_DB_PATH",
        default_path="data/ai_gateway.db",
        tier=BackupTier.STANDARD,
        description="AI gateway request log and token budget state",
    ),
    # ── LOW ─────────────────────────────────────────────────────────────────────
    WorkerDB(
        worker="analytics-service",
        env_var="ANALYTICS_DB_PATH",
        default_path="data/analytics.db",
        tier=BackupTier.LOW,
        description="Event analytics (re-derivable from audit log)",
    ),
    WorkerDB(
        worker="cache-service",
        env_var="CACHE_DB_PATH",
        default_path="data/cache.db",
        tier=BackupTier.LOW,
        description="Distributed cache (ephemeral by design)",
    ),
    WorkerDB(
        worker="rate-limit-service",
        env_var="RATELIMIT_DB_PATH",
        default_path="data/ratelimit.db",
        tier=BackupTier.LOW,
        description="Token-bucket rate limiter state (ephemeral)",
    ),
    WorkerDB(
        worker="cdn-service",
        env_var="CDN_DB_PATH",
        default_path="data/cdn.db",
        tier=BackupTier.LOW,
        description="Static asset routing metadata",
    ),
    WorkerDB(
        worker="geo-service",
        env_var="GEO_DB_PATH",
        default_path="data/geo.db",
        tier=BackupTier.LOW,
        description="Geographic routing table",
    ),
    WorkerDB(
        worker="health-aggregator",
        env_var="HEALTH_AGG_DB_PATH",
        default_path="data/health.db",
        tier=BackupTier.LOW,
        description="Platform-wide health roll-up history",
    ),
    WorkerDB(
        worker="topology-service",
        env_var="TOPOLOGY_DB_PATH",
        default_path="data/topology.db",
        tier=BackupTier.LOW,
        description="Service topology graph",
    ),
]

# Convenience lookups
REGISTRY_BY_WORKER: dict[str, WorkerDB] = {w.worker: w for w in WORKER_DATABASE_REGISTRY}
REGISTRY_BY_TIER: dict[BackupTier, list[WorkerDB]] = {
    tier: [w for w in WORKER_DATABASE_REGISTRY if w.tier == tier] for tier in BackupTier
}
