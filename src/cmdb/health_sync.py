"""Sync health-aggregator's poll results into CMDB.HealthObservation.

health-aggregator (workers/health-aggregator/worker.py, port 8029) already
polls ~40 services every 30s and stores results in its own SQLite DB
(health_checks / health_history tables). This module maps those rows onto
CMDB ServiceIDs and writes HealthObservation rows, so the trend-detection
work described in OBSERVABILITY-AND-AUTOMATION-GOVERNANCE.md has real,
queryable data to read from instead of nothing.

Mapping problem: health-aggregator identifies services by their compose
service name ("infinity-portal"), CMDB identifies them by ServiceID
("SRV-PORTAL-001"). There is no shared key column. Two name-based
approaches were tried and rejected before landing on a port join:

  1. Fuzzy-match worker directory / compose names against ServiceName /
     Notes text. Rejected — this produced two confirmed wrong matches
     earlier in this session (blender-worker and tranc3-ai both matched
     the wrong row because an unrelated row's Notes happened to mention
     their name in a cross-reference, e.g. a port-conflict note).

  2. Join on `health_checks.service` against a static copy of
     health-aggregator's SERVICE_REGISTRY names. Rejected on PR review
     (#223) — health-aggregator also accepts *dynamic* registrations via
     POST /services (scripts/register_ea_workbook_services.py), which
     register under the CSV's `ServiceName` (e.g. "MCP Server"), not the
     compose name. Those rows' `service` value would never match the
     static registry, and worse, `since_id` still advances past them, so
     they'd be unrecoverable without manually rewinding the marker.

The join actually used: **port number**, read directly from
`health_checks.port` — which health-aggregator populates for both static
*and* dynamic targets (`_dynamic_poll_targets()` derives a real port from
the registered URL). Every CMDB Service.notes field that documents a
verified port mentions that port as the FIRST 4-5 digit number following
the word "port" (later mentions in the same Notes field are
cross-references to *other* services' ports, e.g. "previously conflicted
with port 8051"). Verified by hand against 7 services with multiple port
mentions in this session — first-mention was correct in all 7.

HEALTH_AGGREGATOR_REGISTRY below is a deliberate static copy of
workers/health-aggregator/worker.py's SERVICE_REGISTRY (name, port) pairs.
It is no longer used to drive the sync itself (see above) — it remains as
a coverage cross-check (how many of health-aggregator's *known static*
targets resolve to a ServiceID) and a drift regression test
(test_registry_does_not_drift_from_health_aggregator_worker).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional, Set

from sqlalchemy.orm import Session

from src.cmdb.models import HealthObservation, Service

logger = logging.getLogger(__name__)

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

# The exact 3 status strings _check_one()/_persist_check() in
# workers/health-aggregator/worker.py actually write to health_checks.status
# ("healthy" | "degraded" | "down") — confirmed by reading that code on PR
# review (#223), not guessed. "unknown" is kept as a defensive fallback for
# any future/unrecognised status value, scoring as None (no signal) rather
# than assuming success or failure.
_STATUS_TO_SCORE = {
    "healthy": 1.0,
    "degraded": 0.5,
    "down": 0.0,
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
    port_to_ids: Dict[int, Set[str]] = {}
    for service_id, notes in session.query(Service.service_id, Service.notes).all():
        port = first_port_in_notes(notes or "")
        if port is None:
            continue
        port_to_ids.setdefault(port, set()).add(service_id)

    clean: Dict[int, str] = {}
    for port, ids in port_to_ids.items():
        if len(ids) == 1:
            clean[port] = next(iter(ids))
        else:
            logger.warning(
                "Port %d is ambiguous across services %s — dropped from the "
                "health-aggregator sync mapping rather than guessed at.",
                port,
                sorted(ids),
            )
    return clean


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

    Joined on `health_checks.port`, not `.service` — health-aggregator
    populates `port` for both statically-registered and dynamically
    registered (POST /services) targets, so this covers both; a name join
    would silently and unrecoverably skip every dynamic registration (see
    module docstring).

    Rows whose port has no CMDB ServiceID match are skipped and counted,
    not guessed at or dropped silently. Each write is deduplicated against
    an existing (service_id, observed_at, source) row so that re-running
    this sync after a crash between the CMDB commit and the marker-file
    update (see scripts/sync_health_aggregator.py) does not insert
    duplicate observations — this script is documented as a scheduled,
    single-runner job, not one safe to run concurrently from multiple
    processes; that stronger guarantee is not implemented here.
    """
    port_to_service_id = build_port_to_service_id(cmdb_session)

    conn = sqlite3.connect(health_aggregator_db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, service, port, status, latency_ms, checked_at, error "
            "FROM health_checks WHERE id > ? ORDER BY id ASC",
            (since_id,),
        ).fetchall()
    finally:
        conn.close()

    written = 0
    skipped_unmapped = 0
    skipped_duplicate = 0
    max_id = since_id

    for row in rows:
        max_id = max(max_id, row["id"])
        service_id = port_to_service_id.get(row["port"])
        if service_id is None:
            skipped_unmapped += 1
            continue

        checked_at = row["checked_at"]
        try:
            # datetime.fromisoformat rejects a bare 'Z' suffix on Python < 3.11.
            if checked_at and checked_at.endswith("Z"):
                checked_at = checked_at[:-1] + "+00:00"
            observed_at = datetime.fromisoformat(checked_at)
        except (TypeError, ValueError):
            logger.warning(
                "Could not parse checked_at %r for service %r (row id %s) — "
                "falling back to current time; this loses the real observation time.",
                row["checked_at"],
                row["service"],
                row["id"],
            )
            observed_at = datetime.now(timezone.utc)

        already_present = (
            cmdb_session.query(HealthObservation.id)
            .filter_by(service_id=service_id, observed_at=observed_at, source="health-aggregator")
            .first()
        )
        if already_present is not None:
            skipped_duplicate += 1
            continue

        latency_ms = row["latency_ms"]
        notes = f"health_checks.id={row['id']}"
        if row["error"]:
            notes += f"; error={row['error']}"
        cmdb_session.add(
            HealthObservation(
                service_id=service_id,
                observed_at=observed_at,
                health_score=_status_to_score(row["status"]),
                status=row["status"],
                error_count=1 if row["error"] else 0,
                response_time_ms=round(latency_ms) if latency_ms is not None else None,
                source="health-aggregator",
                notes=notes,
            )
        )
        written += 1

    cmdb_session.commit()
    known_static_names = build_health_aggregator_name_to_service_id(cmdb_session)
    return {
        "rows_read": len(rows),
        "written": written,
        "skipped_unmapped": skipped_unmapped,
        "skipped_duplicate": skipped_duplicate,
        "max_id": max_id,
        "mapped_static_registry_services": len(known_static_names),
        "unmapped_static_registry_entries": len(HEALTH_AGGREGATOR_REGISTRY)
        - len(known_static_names),
    }
