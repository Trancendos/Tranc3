"""
Dimensional.architecture.audit_ledger — Append-only signed records for compliance.

Implements a tamper-evident audit ledger that records security-relevant events
in an append-only data structure with cryptographic chain verification.

Properties:
    - Append-only: Records can only be added, never modified or deleted
    - Chained: Each record includes a hash of the previous record
    - Signed: Each record includes a signature for tamper detection
    - Verifiable: The entire chain can be verified for integrity
    - Efficient: Uses SHA-256 for chaining, HMAC for signing

The ledger stores records as JSONL files (one record per line) in a
designated directory. This makes the audit trail human-readable and
easy to back up.

Usage:
    from Dimensional.architecture.audit_ledger import AuditLedger, AuditRecord

    ledger = AuditLedger(storage_dir="logs/audit")

    # Record an event
    record = ledger.append(
        event_type="security_scan",
        actor="ci-pipeline",
        details={"violations_found": 0, "scan_duration": 12.5},
    )

    # Verify the entire chain
    is_valid = ledger.verify_chain()
    print(f"Chain integrity: {is_valid}")

    # Query records
    recent = ledger.query(event_type="security_scan", limit=10)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_STORAGE_DIR = "logs/audit"
_LEDGER_FILE = "ledger.jsonl"
_CHAIN_FILE = "chain_state.json"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class AuditRecord:
    """A single record in the audit ledger.

    Each record is immutable once created. The chain_hash links it to
    the previous record, creating a tamper-evident chain.
    """

    record_id: str
    timestamp: str
    event_type: str
    actor: str
    details: Dict[str, Any]
    chain_hash: str = ""
    record_hash: str = ""
    sequence_number: int = 0

    def to_json(self) -> str:
        """Serialize to a single JSON line for JSONL storage."""
        d = asdict(self)
        return json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "AuditRecord":
        """Deserialize from a JSONL line."""
        data = json.loads(line)
        return cls(**data)


# ---------------------------------------------------------------------------
# AuditLedger
# ---------------------------------------------------------------------------


class AuditLedger:
    """Append-only signed audit ledger for compliance.

    Records security-relevant events in a tamper-evident chain. Each
    record includes:
        - A SHA-256 hash of the record content
        - A chain hash linking to the previous record
        - An HMAC signature using a signing key

    The chain can be verified at any time to detect tampering.

    Storage format:
        - ledger.jsonl: One JSON record per line (append-only)
        - chain_state.json: Current chain state (last hash, sequence number)
    """

    def __init__(
        self,
        *,
        storage_dir: str = _DEFAULT_STORAGE_DIR,
        signing_key: Optional[str] = None,
    ):
        """Initialize the audit ledger.

        Args:
            storage_dir: Directory for storing ledger files.
            signing_key: Key for HMAC signing. If None, reads from
                AUDIT_SIGNING_KEY env var or generates a random key.
        """
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

        self._ledger_path = self._storage_dir / _LEDGER_FILE
        self._chain_path = self._storage_dir / _CHAIN_FILE

        # Signing key for HMAC
        self._signing_key = signing_key or os.getenv("AUDIT_SIGNING_KEY", "")
        if not self._signing_key:
            # Generate a key from machine-specific entropy.
            # WARNING: This key is not portable — ledger verification requires
            # the AUDIT_SIGNING_KEY env var to be explicitly set for multi-node
            # or disaster-recovery scenarios. The fallback key combines hostname,
            # process ID, and boot time to reduce collision risk across machines.
            import socket
            import time

            key_source = f"tranc3-audit-{socket.gethostname()}-{os.getpid()}-{time.time()}"
            self._signing_key = hashlib.sha256(key_source.encode()).hexdigest()[:32]
            import warnings

            warnings.warn(
                "AuditLedger: Using auto-generated signing key. Set AUDIT_SIGNING_KEY "
                "env var for reproducible verification across restarts or multi-node deploys.",
                stacklevel=2,
            )

        # Load chain state
        self._last_hash = "genesis"  # Hash of the most recent record
        self._sequence = 0
        self._load_chain_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(
        self,
        *,
        event_type: str,
        actor: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditRecord:
        """Append a new record to the audit ledger.

        Args:
            event_type: Type of event (e.g., "security_scan", "config_change").
            actor: Who or what initiated the event (e.g., "ci-pipeline", "admin").
            details: Additional details about the event.

        Returns:
            The created AuditRecord.
        """
        self._sequence += 1
        now = datetime.now(timezone.utc).isoformat()

        record = AuditRecord(
            record_id=self._generate_record_id(now, event_type),
            timestamp=now,
            event_type=event_type,
            actor=actor,
            details=details or {},
            sequence_number=self._sequence,
        )

        # Compute record hash
        record.record_hash = self._compute_record_hash(record)

        # Chain to previous record
        record.chain_hash = self._compute_chain_hash(record, self._last_hash)

        # Update chain state
        self._last_hash = record.chain_hash

        # Persist
        self._append_to_ledger(record)
        self._save_chain_state()

        logger.debug(
            "Audit record #%d: %s by %s",
            record.sequence_number,
            record.event_type,
            record.actor,
        )

        return record

    def verify_chain(self) -> bool:
        """Verify the integrity of the entire audit chain.

        Checks that:
            1. Each record's hash is correct
            2. Each record's chain_hash links to the previous record
            3. No records have been modified or removed
            4. The sequence numbers are contiguous

        Returns:
            True if the chain is intact, False if tampering is detected.
        """
        records = self._read_all_records()
        if not records:
            return True  # Empty chain is valid

        expected_hash = "genesis"

        for i, record in enumerate(records):
            # Verify sequence number
            if record.sequence_number != i + 1:
                logger.error(
                    "Chain integrity violation: expected sequence %d, got %d",
                    i + 1,
                    record.sequence_number,
                )
                return False

            # Verify record hash
            expected_record_hash = self._compute_record_hash(record)
            if record.record_hash != expected_record_hash:
                logger.error(
                    "Chain integrity violation: record %d hash mismatch",
                    record.sequence_number,
                )
                return False

            # Verify chain hash
            expected_chain_hash = self._compute_chain_hash(record, expected_hash)
            if record.chain_hash != expected_chain_hash:
                logger.error(
                    "Chain integrity violation: record %d chain hash mismatch",
                    record.sequence_number,
                )
                return False

            expected_hash = record.chain_hash

        # Verify against stored chain state
        if expected_hash != self._last_hash:
            logger.error("Chain integrity violation: final hash doesn't match stored state")
            return False

        return True

    def query(
        self,
        *,
        event_type: Optional[str] = None,
        actor: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditRecord]:
        """Query audit records with optional filters.

        Args:
            event_type: Filter by event type.
            actor: Filter by actor.
            since: ISO timestamp — only return records after this time.
            limit: Maximum number of records to return.

        Returns:
            List of matching AuditRecord objects (most recent first).
        """
        records = self._read_all_records()
        results = []

        for record in reversed(records):
            if event_type and record.event_type != event_type:
                continue
            if actor and record.actor != actor:
                continue
            if since and record.timestamp < since:
                continue
            results.append(record)
            if len(results) >= limit:
                break

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Return statistics about the audit ledger."""
        records = self._read_all_records()
        event_types = {}
        actors = {}
        for r in records:
            event_types[r.event_type] = event_types.get(r.event_type, 0) + 1
            actors[r.actor] = actors.get(r.actor, 0) + 1

        return {
            "total_records": len(records),
            "first_record": records[0].timestamp if records else None,
            "last_record": records[-1].timestamp if records else None,
            "event_types": event_types,
            "actors": actors,
            "chain_valid": self.verify_chain(),
            "storage_dir": str(self._storage_dir),
        }

    def get_record_count(self) -> int:
        """Return the total number of records in the ledger."""
        return self._sequence

    # ------------------------------------------------------------------
    # Internal: hashing
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_record_id(timestamp: str, event_type: str) -> str:
        """Generate a unique record ID."""
        source = f"{timestamp}:{event_type}:{os.urandom(8).hex()}"
        return hashlib.sha256(source.encode()).hexdigest()[:16]

    @staticmethod
    def _compute_record_hash(record: AuditRecord) -> str:
        """Compute SHA-256 hash of a record's content."""
        # Hash the immutable fields (exclude hashes themselves)
        content = json.dumps(
            {
                "record_id": record.record_id,
                "timestamp": record.timestamp,
                "event_type": record.event_type,
                "actor": record.actor,
                "details": record.details,
                "sequence_number": record.sequence_number,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(content.encode()).hexdigest()

    def _compute_chain_hash(self, record: AuditRecord, previous_hash: str) -> str:
        """Compute the chain hash linking this record to the previous one."""
        chain_content = f"{previous_hash}:{record.record_hash}"
        raw_hash = hashlib.sha256(chain_content.encode()).digest()

        # Add HMAC signature
        signature = hmac.new(
            self._signing_key.encode(),  # type: ignore[union-attr]
            raw_hash,
            hashlib.sha256,
        ).hexdigest()

        return signature

    # ------------------------------------------------------------------
    # Internal: persistence
    # ------------------------------------------------------------------

    def _append_to_ledger(self, record: AuditRecord) -> None:
        """Append a record to the JSONL ledger file."""
        with open(self._ledger_path, "a", encoding="utf-8") as f:
            f.write(record.to_json() + "\n")

    def _read_all_records(self) -> List[AuditRecord]:
        """Read all records from the ledger file."""
        if not self._ledger_path.exists():
            return []

        records = []
        try:
            with open(self._ledger_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(AuditRecord.from_json(line))
                        except (json.JSONDecodeError, TypeError) as e:
                            logger.error("Corrupt ledger entry: %s", e)
        except OSError as e:
            logger.error("Failed to read ledger: %s", e)

        return records

    def _load_chain_state(self) -> None:
        """Load the chain state from disk."""
        if not self._chain_path.exists():
            return

        try:
            data = json.loads(self._chain_path.read_text(encoding="utf-8"))
            self._last_hash = data.get("last_hash", "genesis")
            self._sequence = data.get("sequence", 0)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load chain state: %s", e)
            self._last_hash = "genesis"
            self._sequence = 0

    def _save_chain_state(self) -> None:
        """Save the chain state to disk."""
        state = {
            "last_hash": self._last_hash,
            "sequence": self._sequence,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._chain_path.write_text(
            json.dumps(state, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
