"""Version 2 canonical audit hashing.

Hashes the complete persisted event, including severity and structured details.
Legacy version 1 hashes are deliberately kept in worker.py for verification of
pre-upgrade records. A hash chain is tamper-evident, NOT immutable; anchoring
chain tips outside the database is still required against full-history rewrite.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_v2_hash(
    prev_hash: str,
    event_id: str,
    timestamp: str,
    service: str,
    action: str,
    actor: str,
    resource: str,
    outcome: str,
    severity: str,
    details_json: str,
) -> str:
    """SHA-256 of a version-tagged, canonical JSON envelope.

    No ambiguous field separators, JSON object key-order dependence, or NaN
    values. Domain/version separation prevents collisions with legacy format.
    """
    details: Any = json.loads(
        details_json,
        parse_constant=lambda v: (_ for _ in ()).throw(ValueError(f"Non-finite JSON value: {v}")),
    )
    if not isinstance(details, dict):
        raise TypeError("Audit event details must be a JSON object")
    envelope = {
        "hash_version": 2,
        "prev_hash": prev_hash,
        "event_id": event_id,
        "timestamp": timestamp,
        "service": service,
        "action": action,
        "actor": actor,
        "resource": resource,
        "outcome": outcome,
        "severity": severity,
        "details": details,
    }
    canonical = json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(("trancendos.audit.v2\n" + canonical).encode("utf-8")).hexdigest()
