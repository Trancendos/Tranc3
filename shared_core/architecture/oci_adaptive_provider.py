"""Backward-compatibility shim.

The canonical implementation now lives in
``Dimensional.architecture.oci_adaptive_provider`` after the
``shared_core`` → ``Dimensional`` rename. This module re-exports the
public symbols, plus the test-referenced private ``_aws_sig4_sign``
helper, so legacy imports of
``shared_core.architecture.oci_adaptive_provider`` keep working.
"""

from __future__ import annotations

from Dimensional.architecture.oci_adaptive_provider import (  # noqa: F401
    OCI_FREE_TIER_LIMITS,
    AdaptiveInstanceDatum,
    AdaptiveProviderConfig,
    CircuitBreaker,
    CircuitState,
    OciAdaptiveProvider,
    OciKeepaliveWorker,
    OciQuotaTracker,
    PersistentInfrastructureDatum,
    StorageTier,
    SystemMode,
    _aws_sig4_sign,
)

__all__ = [
    "OCI_FREE_TIER_LIMITS",
    "AdaptiveInstanceDatum",
    "AdaptiveProviderConfig",
    "CircuitBreaker",
    "CircuitState",
    "OciAdaptiveProvider",
    "OciKeepaliveWorker",
    "OciQuotaTracker",
    "PersistentInfrastructureDatum",
    "StorageTier",
    "SystemMode",
    "_aws_sig4_sign",
]
