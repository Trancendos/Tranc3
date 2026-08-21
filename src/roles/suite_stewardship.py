# src/roles/suite_stewardship.py
"""Matrix Suite stewardship — Matrix Suites Stage 7.5.

docs/governance/MATRIX-SUITES.md §3 (Magna Carta submodule) already states the
intended design: "Suite stewardship follows the same rule [as Location Job
Descriptions]: the registry is authoritative at runtime; [matrix_suites.yaml]
records the baseline it is seeded from." This module is that cross-reference,
not a second registry.

Why not just insert 8 new rows into role_assignments? Each suite's
steward_location is already one of the 43 canonical Locations, which already
owns a row in the Role Registry (src/roles/registry.py) keyed on `location` as
a primary key sourced from PLATFORM_ENTITIES — assign_ai()/remove_ai()/
get_history() all reject any location that isn't one. A suite isn't a
Location; giving it its own row would either corrupt that 1:1 model with a
fake pseudo-location or stand up a second, unsynced audit trail that could
silently drift from the real Location assignment it's supposed to describe.

Instead, "who currently stewards Suite X" is answered by reading the suite's
designed baseline from Magna Carta's matrix_suites.yaml and the LIVE
assigned_ai at that suite's steward_location from the existing Role Registry.
If a Location's operator reassigns the AI there, this view reflects it
immediately with zero extra bookkeeping — and a `drifted` suite (live holder
no longer matches the design doc's baseline) is a more honest, more useful
signal than a second static copy of the same fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from src.compliance.matrix_suites import (
    MatrixSuitesError,
    MatrixSuitesRegistryError,
    load_suites,
)
from src.roles.registry import get_registry


@dataclass
class SuiteStewardship:
    suite_id: str
    name: str
    pillar: str
    steward_location: str
    designed_steward_ai: str
    current_steward_ai: Optional[str]
    presiding_prime: str
    escalation: List[str]
    review_cadence: str
    next_review: str
    drifted: bool


def _coerce_str_list(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return []


def list_suite_stewardships(matrix_suites_path: Optional[str] = None) -> List[SuiteStewardship]:
    """Cross-reference every Suite's designed steward against the live Role Registry.

    A missing registry file is not an error — load_suites() returns [] for it,
    and this function passes that empty list straight through, same as an
    estate with zero defined suites would look. A *malformed* registry file
    (invalid YAML, wrong root/field shape, or a non-mapping suite entry) does
    raise MatrixSuitesError (a MatrixSuitesRegistryError specifically), which
    callers map to an HTTP error rather than silently returning an empty list
    — matching how src/compliance/matrix_suites_routes.py treats the same
    underlying failure.
    """
    suites = load_suites(matrix_suites_path)
    registry = get_registry()
    results: List[SuiteStewardship] = []
    for suite in suites:
        if not isinstance(suite, dict):
            raise MatrixSuitesRegistryError("matrix_suites.yaml: each suite must be a mapping")
        steward_location = str(suite.get("steward_location") or "")
        designed_ai = str(suite.get("steward_ai") or "")
        role = registry.get_role(steward_location) if steward_location else None
        current_ai = role.assigned_ai if role else None
        results.append(
            SuiteStewardship(
                suite_id=str(suite.get("suite_id") or ""),
                name=str(suite.get("name") or ""),
                pillar=str(suite.get("pillar") or ""),
                steward_location=steward_location,
                designed_steward_ai=designed_ai,
                current_steward_ai=current_ai,
                presiding_prime=str(suite.get("presiding_prime") or ""),
                escalation=_coerce_str_list(suite.get("escalation")),
                review_cadence=str(suite.get("review_cadence") or ""),
                next_review=str(suite.get("next_review") or ""),
                drifted=current_ai != designed_ai,
            )
        )
    return results


def get_suite_stewardship(
    suite_id: str, matrix_suites_path: Optional[str] = None
) -> Optional[SuiteStewardship]:
    """Look up one Suite's stewardship by ID.

    Mirrors src/compliance/matrix_suites.py's _find_suite(): two registry
    entries sharing one suite_id is a broken registry, not "pick the first
    one" — silently resolving to whichever came first could point a caller
    at the wrong suite's escalation chain/steward entirely. Raises
    MatrixSuitesRegistryError in that case rather than returning a match.
    """
    matches = [s for s in list_suite_stewardships(matrix_suites_path) if s.suite_id == suite_id]
    if len(matches) > 1:
        raise MatrixSuitesRegistryError(
            f"Ambiguous suite_id (registry has duplicates): {suite_id!r}"
        )
    return matches[0] if matches else None


__all__ = [
    "SuiteStewardship",
    "list_suite_stewardships",
    "get_suite_stewardship",
    "MatrixSuitesError",
]
