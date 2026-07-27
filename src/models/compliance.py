# src/models/compliance.py
"""Trancendos Models Matrix <-> Magna-Carta license/provenance gate.

Mirrors (does not live-couple to) Magna-Carta's MC-013 Intellectual
Property Matrix — specifically its `training_data_provenance` risk
entries in `compliance/estate_protection_matrices.yaml` — into a
pre-flight check the Models Matrix governance pipeline
(`src/models/governance.py`) runs before accepting a new advancement
proposal. This is the same "Tranc3-side pointer/summary" pattern already
used by `docs/governance/ESTATE-PROTECTION-MATRICES.md` for MC-012-015:
Magna-Carta is a separate repository/submodule, so its findings are
mirrored here as data rather than imported live.

MC-012 (License Compliance Matrix) is deliberately NOT wired in here: it's
a repo-wide dependency license scan (pip-licenses, 190 packages, already
enforced in CI via `.forgejo/workflows/dependency-audit.yml`) with no
natural per-model-advancement scope — there's no such thing as "this AI's
advancement violates a package license." MC-013's training-data-provenance
risk, by contrast, genuinely is scoped to specific AIs' generated output,
which is exactly what an advancement proposal is about.

Two kinds of risk exist in MC-013's register:

    AI-specific (gates `submit_proposal()`):
        A risk tied to one named AI's own generated output — e.g. Sashas
        Photo Studio's Madam Krystal, whose ComfyUI/A1111 backend output
        has an open, not-yet-assessed training-data-provenance review.
        Submitting an advancement proposal for that AI is blocked until
        the risk is cleared.

    Platform-wide (advisory only, never blocks):
        A risk tied to shared infrastructure every AI depends on (e.g.
        the AI Gateway's HuggingFace/OpenRouter free-tier model outputs).
        Gating every single AI's advancement on a platform-wide caveat
        would make the governance pipeline unusable, so these are surfaced
        for read-only awareness (`platform_wide_risks()`) and never raise.

Clearing a risk is admin-gated and SQLite-backed
(`ProvenanceClearanceRegistry`) rather than requiring a code change and
redeploy every time a real-world provenance review actually completes.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_DB_PATH = Path("data/models_provenance.db")


class ProvenanceStatus(str, Enum):
    NOT_ASSESSED = "not_assessed"
    VERIFIED_CAVEAT = "verified_caveat"
    CLEARED = "cleared"


class OpenProvenanceRiskError(ValueError):
    """Raised by governance.submit_proposal() when the target AI has an
    open (NOT_ASSESSED) MC-013 training-data-provenance risk that hasn't
    been cleared via ProvenanceClearanceRegistry.clear()."""


@dataclass(frozen=True)
class ProvenanceRisk:
    ai_name: Optional[str]  # None for platform-wide risks
    entity: str
    risk: str
    status: ProvenanceStatus
    note: str
    mc_reference: str = "MC-013"


@dataclass
class ProvenanceCheckResult:
    cleared: bool
    risk: Optional[ProvenanceRisk]


# Seeded from Magna-Carta's compliance/estate_protection_matrices.yaml
# `intellectual_property.non_infringement_risks` (training_data_provenance
# entries only — naming_collision risks aren't provenance-relevant here).
# Mirrored, not live-coupled — see module docstring.
_AI_SPECIFIC_RISKS: Dict[str, ProvenanceRisk] = {
    "Madam Krystal": ProvenanceRisk(
        ai_name="Madam Krystal",
        entity="Sashas Photo Studio Stable Diffusion/ComfyUI backend",
        risk="training_data_provenance",
        status=ProvenanceStatus.NOT_ASSESSED,
        note=(
            "workers/sashas-photo-studio/main.py has a live ComfyUI-primary/A1111-fallback "
            "HTTP integration against self-hosted instances. No copyleft code-redistribution "
            "obligation (HTTP orchestration, not embedded GPL-3.0/AGPL-3.0 source), but the "
            "training-data-provenance review on generated output is due, not deferrable."
        ),
    ),
}

_PLATFORM_WIDE_RISKS: List[ProvenanceRisk] = [
    ProvenanceRisk(
        ai_name=None,
        entity="AI Gateway model outputs (HuggingFace/OpenRouter free tiers)",
        risk="training_data_provenance",
        status=ProvenanceStatus.NOT_ASSESSED,
        note=(
            "Shared inference substrate every AI depends on — advisory only, never gates a "
            "single AI's advancement proposal (see module docstring)."
        ),
    ),
]


def platform_wide_risks() -> List[ProvenanceRisk]:
    """Read-only, advisory MC-013 risks that apply platform-wide rather
    than to one named AI. Never blocks anything."""
    return list(_PLATFORM_WIDE_RISKS)


def _emit_provenance_event(event_type: str, ai_name: str, **extra) -> None:
    """Best-effort audit trail via The Observatory — see
    governance._emit_governance_event()'s identical non-fatal pattern."""
    try:
        from src.observability.observatory import EventCategory, EventSeverity, observe

        observe(
            event_type,
            actor=extra.pop("cleared_by", "system"),
            target=f"model:{ai_name}",
            category=EventCategory.GOVERNANCE,
            severity=EventSeverity.INFO,
            metadata={"ai_name": ai_name, **extra},
        )
    except Exception:
        pass


class ProvenanceClearanceRegistry:
    """SQLite-backed overrides for AI-specific MC-013 risks — lets an
    admin record that a real-world provenance review has completed
    without needing a code change to this module's seed data."""

    def __init__(self, db_path: "str | Path" = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS provenance_clearances (
                ai_name TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                cleared_by TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                cleared_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def clear(
        self,
        ai_name: str,
        cleared_by: str,
        notes: str = "",
        status: ProvenanceStatus = ProvenanceStatus.CLEARED,
    ) -> None:
        """Record that `ai_name`'s open provenance risk has been reviewed.
        `status` may be CLEARED or VERIFIED_CAVEAT — both unblock
        submit_proposal(); only NOT_ASSESSED (the default/seed state)
        blocks it."""
        with self._lock:
            now = time.time()
            self._conn.execute(
                "INSERT INTO provenance_clearances (ai_name, status, cleared_by, notes, cleared_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(ai_name) DO UPDATE SET "
                "status=excluded.status, cleared_by=excluded.cleared_by, "
                "notes=excluded.notes, cleared_at=excluded.cleared_at",
                (ai_name, status.value, cleared_by, notes, now),
            )
            self._conn.commit()
        _emit_provenance_event(
            "model.provenance.cleared", ai_name, cleared_by=cleared_by, status=status.value
        )

    def get_override(self, ai_name: str) -> Optional[Dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM provenance_clearances WHERE ai_name = ?", (ai_name,)
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def close(self) -> None:
        self._conn.close()


_registry: Optional[ProvenanceClearanceRegistry] = None
_registry_lock = threading.Lock()


def get_clearance_registry() -> ProvenanceClearanceRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = ProvenanceClearanceRegistry()
    return _registry


def check_provenance(
    ai_name: str, clearance_registry: Optional[ProvenanceClearanceRegistry] = None
) -> ProvenanceCheckResult:
    """Is `ai_name` clear to have an advancement proposal submitted?

    Looks up any AI-specific seed risk (`_AI_SPECIFIC_RISKS`), then checks
    for an admin-recorded override in ProvenanceClearanceRegistry. An AI
    with no seed risk at all is always cleared. Never touches
    `_PLATFORM_WIDE_RISKS` — those are advisory-only, see module
    docstring."""
    seed_risk = _AI_SPECIFIC_RISKS.get(ai_name)
    if seed_risk is None:
        return ProvenanceCheckResult(cleared=True, risk=None)

    registry = clearance_registry or get_clearance_registry()
    override = registry.get_override(ai_name)
    if override is not None:
        effective_status = ProvenanceStatus(override["status"])
        effective_risk = ProvenanceRisk(
            ai_name=seed_risk.ai_name,
            entity=seed_risk.entity,
            risk=seed_risk.risk,
            status=effective_status,
            note=f"{seed_risk.note} [cleared by {override['cleared_by']}: {override['notes']}]",
            mc_reference=seed_risk.mc_reference,
        )
        return ProvenanceCheckResult(
            cleared=effective_status != ProvenanceStatus.NOT_ASSESSED, risk=effective_risk
        )

    return ProvenanceCheckResult(
        cleared=seed_risk.status != ProvenanceStatus.NOT_ASSESSED, risk=seed_risk
    )
