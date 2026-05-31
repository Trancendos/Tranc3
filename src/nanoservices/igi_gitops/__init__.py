"""
IGI — Immutable GitOps Infrastructure Package
==============================================
Uses Forgejo (NOT GitHub) as the Git source of truth.
"""

from .igi_gitops import (
    DriftDetector,
    DriftEvent,
    DriftSeverity,
    FluxSyncStatus,
    ForgejoConfig,
    GitOpsStatus,
    IGIGitOps,
    KustomizeOverlay,
    ResourceType,
)

__all__ = [
    "GitOpsStatus",
    "DriftSeverity",
    "ResourceType",
    "ForgejoConfig",
    "FluxSyncStatus",
    "DriftEvent",
    "KustomizeOverlay",
    "DriftDetector",
    "IGIGitOps",
]
