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
from pathlib import Path
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
    # True when `env_var` holds a data *directory* (e.g. VOID_DATA_DIR,
    # MLFLOW_DATA_DIR) rather than a direct file path — the worker itself
    # appends the same filename as default_path's basename onto that
    # directory. Without this, resolved_path would point at a directory
    # instead of the actual .db file whenever the env var is set.
    env_var_is_dir: bool = False

    @property
    def resolved_path(self) -> str:
        override = os.environ.get(self.env_var)
        if override is None:
            return self.default_path
        if self.env_var_is_dir:
            return str(Path(override) / Path(self.default_path).name)
        return override

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
    WorkerDB(
        worker="infinity-void",
        env_var="VOID_DATA_DIR",
        default_path="/data/void/void.db",
        tier=BackupTier.CRITICAL,
        description="The Void — self-hosted AES-GCM secrets vault (standalone worker)",
        env_var_is_dir=True,
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
    WorkerDB(
        worker="cryptex",
        env_var="CRYPTEX_DB_PATH",
        default_path="/data/cryptex.db",
        tier=BackupTier.HIGH,
        description="Cyber defense — threat intel, DDoS, CVE tracking",
    ),
    WorkerDB(
        worker="ice-box-service",
        env_var="ICE_BOX_QUARANTINE_DB",
        default_path="data/ice_box_quarantine.db",
        tier=BackupTier.HIGH,
        description="Sandbox threat isolation & quarantine store",
    ),
    WorkerDB(
        worker="observatory",
        env_var="OBSERVATORY_DB_PATH",
        default_path="/data/observatory.db",
        tier=BackupTier.HIGH,
        description="The Observatory audit trail (standalone worker variant)",
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
    WorkerDB(
        worker="dimensional-nexus-service",
        env_var="NEXUS_DB_PATH",
        default_path="data/nexus.db",
        tier=BackupTier.STANDARD,
        description="Dimensional Nexus — multi-dimensional data routing state",
    ),
    WorkerDB(
        worker="hive-service",
        env_var="HIVE_DB_PATH",
        default_path="data/hive.db",
        tier=BackupTier.STANDARD,
        description="The HIVE task queue coordination (library variant)",
    ),
    WorkerDB(
        worker="gateway-service",
        env_var="GATEWAY_DB_PATH",
        default_path="data/gateway.db",
        tier=BackupTier.STANDARD,
        description="API gateway routing/session state",
    ),
    WorkerDB(
        worker="model-router-service",
        env_var="MODEL_ROUTER_DB_PATH",
        default_path="data/model_router.db",
        tier=BackupTier.STANDARD,
        description="AI model routing decisions",
    ),
    WorkerDB(
        worker="skills-benchmark-service",
        env_var="BENCHMARK_DB_PATH",
        default_path="data/benchmark.db",
        tier=BackupTier.STANDARD,
        description="Turing's Hub skill benchmark results",
    ),
    WorkerDB(
        worker="langchain-integration-service",
        env_var="LANGCHAIN_DB_PATH",
        default_path="data/langchain.db",
        tier=BackupTier.STANDARD,
        description="LangChain chain/RAG/agent orchestration state",
    ),
    WorkerDB(
        worker="haystack-service",
        env_var="HAYSTACK_DB_PATH",
        default_path="data/haystack.db",
        tier=BackupTier.STANDARD,
        description="Haystack production RAG pipeline state",
    ),
    WorkerDB(
        worker="llamaindex-service",
        env_var="LLAMAINDEX_DB_PATH",
        default_path="data/llamaindex.db",
        tier=BackupTier.STANDARD,
        description="LlamaIndex document Q&A index metadata",
    ),
    WorkerDB(
        worker="dspy-service",
        env_var="DSPY_DB_PATH",
        default_path="data/dspy.db",
        tier=BackupTier.STANDARD,
        description="DSPy programmatic prompt compiler state",
    ),
    WorkerDB(
        worker="deepagents-orchestrator-service",
        env_var="DEEPAGENTS_DB_PATH",
        default_path="deepagents.db",
        tier=BackupTier.STANDARD,
        description="Deep agent orchestration state",
    ),
    WorkerDB(
        worker="mlflow-service",
        env_var="MLFLOW_DATA_DIR",
        default_path="/data/mlflow-service/mlflow.db",
        tier=BackupTier.STANDARD,
        description="MLflow experiment tracking store",
        env_var_is_dir=True,
    ),
    WorkerDB(
        worker="litellm-service",
        env_var="LITELLM_DB_PATH",
        default_path="litellm_usage.db",
        tier=BackupTier.STANDARD,
        description="LiteLLM zero-cost AI proxy usage log (x10 provider rotation)",
    ),
    WorkerDB(
        worker="gbrain-bridge",
        env_var="GBRAIN_DB_PATH",
        default_path="data/gbrain.db",
        tier=BackupTier.STANDARD,
        description="GBrain AI bridge state",
    ),
    WorkerDB(
        worker="the-dutchy",
        env_var="DUTCHY_DB_PATH",
        default_path="data/dutchy.db",
        tier=BackupTier.STANDARD,
        description="The Dutchy — intelligence & market analysis data",
    ),
    WorkerDB(
        worker="the-academy",
        env_var="ACADEMY_DB_PATH",
        default_path="data/academy.db",
        tier=BackupTier.STANDARD,
        description="The Academy learning management records",
    ),
    WorkerDB(
        worker="the-lab",
        env_var="THE_LAB_DB_PATH",
        default_path="data/lab.db",
        tier=BackupTier.STANDARD,
        description="The Lab code creation platform state",
    ),
    WorkerDB(
        worker="lab-service",
        env_var="LAB_DB_PATH",
        default_path="/data/lab.db",
        tier=BackupTier.STANDARD,
        description="The Lab extended service layer state",
    ),
    WorkerDB(
        worker="library-service",
        env_var="LIBRARY_DB_PATH",
        default_path="/data/library.db",
        tier=BackupTier.STANDARD,
        description="The Library knowledge base (standalone worker variant)",
    ),
    WorkerDB(
        worker="devocity",
        env_var="DEVOCITY_DB_PATH",
        default_path="data/devocity.db",
        tier=BackupTier.STANDARD,
        description="DevOcity development ops hub state",
    ),
    WorkerDB(
        worker="imaginarium",
        env_var="IMAGINARIUM_DB_PATH",
        default_path="data/imaginarium.db",
        tier=BackupTier.STANDARD,
        description="Imaginarium omni-creative orchestration state",
    ),
    WorkerDB(
        worker="imind",
        env_var="IMIND_DB_PATH",
        default_path="data/imind.db",
        tier=BackupTier.STANDARD,
        description="I-Mind emotion sensitivity engine state",
    ),
    WorkerDB(
        worker="taimra",
        env_var="TAIMRA_DB_PATH",
        default_path="data/taimra.db",
        tier=BackupTier.STANDARD,
        description="tAimra digital twin state",
    ),
    WorkerDB(
        worker="tateking",
        env_var="TATEKING_DB_PATH",
        default_path="data/tateking.db",
        tier=BackupTier.STANDARD,
        description="TateKing video creation project state",
    ),
    WorkerDB(
        worker="the-studio",
        env_var="STUDIO_DB_PATH",
        default_path="data/studio.db",
        tier=BackupTier.STANDARD,
        description="The Studio central creativity hub state",
    ),
    WorkerDB(
        worker="tranceflow",
        env_var="TRANCEFLOW_DB_PATH",
        default_path="/data/tranceflow.db",
        tier=BackupTier.STANDARD,
        description="TranceFlow 3D/game creation state",
    ),
    WorkerDB(
        worker="vrar3d",
        env_var="VRAR3D_DB_PATH",
        default_path="/data/vrar3d.db",
        tier=BackupTier.STANDARD,
        description="VRAR3D immersion session state",
    ),
    WorkerDB(
        worker="resonate",
        env_var="RESONATE_DB_PATH",
        default_path="data/resonate.db",
        tier=BackupTier.STANDARD,
        description="Resonate empathy engine state",
    ),
    WorkerDB(
        worker="tranquility",
        env_var="TRANQUILITY_DB_PATH",
        default_path="data/tranquility.db",
        tier=BackupTier.STANDARD,
        description="Tranquility wellbeing hub state",
    ),
    WorkerDB(
        worker="warp-radio",
        env_var="WARP_RADIO_DB_PATH",
        default_path="data/radio.db",
        tier=BackupTier.STANDARD,
        description="Warp Radio playlist/station state",
    ),
    WorkerDB(
        worker="warp-tunnel",
        env_var="WARP_TUNNEL_DB_PATH",
        default_path="data/warp_tunnel.db",
        tier=BackupTier.STANDARD,
        description="The Warp Tunnel — crypto scanner/quarantine transport log",
    ),
    WorkerDB(
        worker="chaos-party",
        env_var="CHAOS_PARTY_DB_PATH",
        default_path="data/chaos.db",
        tier=BackupTier.STANDARD,
        description="The Chaos Party testing/validation results",
    ),
    WorkerDB(
        worker="sms-service",
        env_var="SMS_DB_PATH",
        default_path="data/sms.db",
        tier=BackupTier.STANDARD,
        description="SMS gateway send queue/delivery log",
    ),
    WorkerDB(
        worker="basement",
        env_var="BASEMENT_DB_PATH",
        default_path="data/basement.db",
        tier=BackupTier.STANDARD,
        description="The Basement — archived info store",
    ),
    # Note: no separate "the-void" entry — workers/the-void/ was an abandoned
    # parallel implementation (never wired into docker-compose.production.yml)
    # and has been deleted (2026-07-30). infinity-void (below) is the canonical
    # deployed Void; vault-service (above, CRITICAL tier) remains deployed but
    # deprecated pending a real secrets migration — see
    # workers/vault-service/DEPRECATED.md and scripts/migrate_vault_secrets.py.
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
    WorkerDB(
        worker="storage-service",
        env_var="STORAGE_DB_PATH",
        default_path="/data/storage.db",
        tier=BackupTier.LOW,
        description="IPFS + local blob storage metadata",
    ),
]

# Convenience lookups
REGISTRY_BY_WORKER: dict[str, WorkerDB] = {w.worker: w for w in WORKER_DATABASE_REGISTRY}
REGISTRY_BY_TIER: dict[BackupTier, list[WorkerDB]] = {
    tier: [w for w in WORKER_DATABASE_REGISTRY if w.tier == tier] for tier in BackupTier
}
