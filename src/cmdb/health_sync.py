"""Sync health-aggregator's poll results into CMDB.HealthObservation.

health-aggregator (workers/health-aggregator/worker.py, port 8029) already
polls ~40 services every 30s and stores results in its own SQLite DB
(health_checks / health_history tables). This module maps those rows onto
CMDB ServiceIDs and writes HealthObservation rows, so the trend-detection
work described in OBSERVABILITY-AND-AUTOMATION-GOVERNANCE.md has real,
queryable data to read from instead of nothing.

Mapping problem: health-aggregator identifies services by their compose
service name ("infinity-portal"), CMDB identifies them by ServiceID
("SRV-PORTAL-001"). There is no shared key column. Two approaches were
tried:

  1. Fuzzy-match worker directory / compose names against ServiceName /
     Notes text. Rejected — this produced two confirmed wrong matches
     earlier in this session (blender-worker and tranc3-ai both matched
     the wrong row because an unrelated row's Notes happened to mention
     their name in a cross-reference, e.g. a port-conflict note).

  2. Match on port number. Every health-aggregator registry entry has an
     unambiguous port; every CMDB Service.notes field that documents a
     verified port mentions that port as the FIRST 4-5 digit number
     following the word "port" (later mentions in the same Notes field
     are cross-references to *other* services' ports, e.g. "previously
     conflicted with port 8051"). Verified by hand against 7 services
     with multiple port mentions in this session — first-mention was
     correct in all 7. This is the approach used here.

HEALTH_AGGREGATOR_REGISTRY below is a deliberate static copy of
workers/health-aggregator/worker.py's SERVICE_REGISTRY (name, port) pairs.
Parsing that file's source at runtime would be more "DRY" but more
fragile (breaks silently if the source is refactored); a static copy that
this module's tests can catch drifting is preferred. Re-copy by hand if
SERVICE_REGISTRY changes.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from src.cmdb.models import HealthObservation, Service

# Kept in sync by hand with workers/health-aggregator/worker.py:SERVICE_REGISTRY.
HEALTH_AGGREGATOR_REGISTRY = [
    ("tranc3-backend", 8000),
    ("tranc3-ai", 8001),
    ("infinity-ws", 8004),
    ("infinity-auth", 8005),
    ("users-service", 8006),
    ("monitoring", 8007),
    ("notifications", 8008),
    ("infinity-ai", 8009),
    ("the-grid", 8010),
    ("products-service", 8011),
    ("orders-service", 8012),
    ("payments-service", 8013),
    ("files-service", 8014),
    ("identity-service", 8015),
    ("analytics-service", 8016),
    ("search-service", 8017),
    ("email-service", 8018),
    ("sms-service", 8019),
    ("storage-service", 8020),
    ("cron-service", 8021),
    ("queue-service", 8022),
    ("cache-service", 8023),
    ("config-service", 8024),
    ("audit-service", 8025),
    ("rate-limit-service", 8026),
    ("geo-service", 8027),
    ("cdn-service", 8028),
    ("gbrain-bridge", 8030),
    ("topology-service", 8031),
    ("ledger-service", 8032),
    ("model-router-service", 8033),
    ("workflow-engine-service", 8034),
    ("skills-benchmark-service", 8035),
    ("langchain-integration-service", 8036),
    ("deepagents-orchestrator-service", 8037),
    ("vault-service", 8038),
    ("infinity-portal", 8042),
    ("infinity-one", 8043),
    ("infinity-admin", 8044),
    ("infinity-shards", 8045),
    ("infinity-bridge", 8070),
    ("cranbania", 8071),
]

_PORT_RE = re.compile(r"\bport (\d{4,5})\b", re.IGNORECASE)

# status values as written by health-aggregator's poller into health_checks.status
_STATUS_TO_SCORE = {
    "healthy": 1.0,
    "degraded": 0.5,
    "unhealthy": 0.0,
    "unreachable": 0.0,
    "timeout": 0.0,
    "error": 0.0,
    "unknown": None,
}


def first_port_in_notes(notes: str) -> Optional[int]:
    """Extract the first 'port NNNN' mention — validated as the service's
    own true port, see module docstring."""
    if not notes:
        return None
    m = _PORT_RE.search(notes)
    return int(m.group(1)) if m else None


def build_port_to_service_id(session: Session) -> Dict[int, str]:
    """{port: ServiceID} from CMDB Service.notes, first-port-mention wins.
    A port that maps to more than one ServiceID is dropped as ambiguous
    rather than guessed at."""
    port_to_ids: Dict[int, set] = {}
    for service_id, notes in session.query(Service.service_id, Service.notes).all():
        port = first_port_in_notes(notes or "")
        if port is None:
            continue
        port_to_ids.setdefault(port, set()).add(service_id)
    return {port: next(iter(ids)) for port, ids in port_to_ids.items() if len(ids) == 1}


def build_health_aggregator_name_to_service_id(session: Session) -> Dict[str, str]:
    """{health-aggregator service name: ServiceID}, joined on port number."""
    port_to_service_id = build_port_to_service_id(session)
    mapping = {}
    for name, port in HEALTH_AGGREGATOR_REGISTRY:
        service_id = port_to_service_id.get(port)
        if service_id is not None:
            mapping[name] = service_id
    return mapping


def _status_to_score(status: str) -> Optional[float]:
    return _STATUS_TO_SCORE.get((status or "").strip().lower())


def sync_from_health_aggregator_db(
    cmdb_session: Session,
    health_aggregator_db_path: str,
    since_id: int = 0,
) -> dict:
    """Read health_checks rows with id > since_id from health-aggregator's
    SQLite DB and write matching HealthObservation rows into cmdb_session.

    Rows whose `service` name has no port-based ServiceID match are
    skipped and counted, not guessed at or dropped silently.
    """
    name_to_service_id = build_health_aggregator_name_to_service_id(cmdb_session)

    conn = sqlite3.connect(health_aggregator_db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, service, status, latency_ms, checked_at, error "
            "FROM health_checks WHERE id > ? ORDER BY id ASC",
            (since_id,),
        ).fetchall()
    finally:
        conn.close()

    written = 0
    skipped_unmapped = 0
    max_id = since_id

    for row in rows:
        max_id = max(max_id, row["id"])
        service_id = name_to_service_id.get(row["service"])
        if service_id is None:
            skipped_unmapped += 1
            continue

        try:
            observed_at = datetime.fromisoformat(row["checked_at"])
        except (TypeError, ValueError):
            observed_at = datetime.now(timezone.utc)

        cmdb_session.add(
            HealthObservation(
                service_id=service_id,
                observed_at=observed_at,
                health_score=_status_to_score(row["status"]),
                status=row["status"],
                error_count=1 if row["error"] else 0,
                response_time_ms=row["latency_ms"],
                source="health-aggregator",
                notes=row["error"] or None,
            )
        )
        written += 1

    cmdb_session.commit()
    return {
        "rows_read": len(rows),
        "written": written,
        "skipped_unmapped": skipped_unmapped,
        "max_id": max_id,
        "mapped_services": len(name_to_service_id),
        "unmapped_registry_entries": len(HEALTH_AGGREGATOR_REGISTRY) - len(name_to_service_id),
    }
