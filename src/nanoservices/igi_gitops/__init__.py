"""
IGI — Immutable GitOps Infrastructure Package
==============================================
Uses Forgejo (NOT GitHub) as the Git source of truth.
"""

from .igi_gitops import (
    GitOpsStatus,
    DriftSeverity,
    ResourceType,
    ForgejoConfig,
    FluxSyncStatus,
    DriftEvent,
    KustomizeOverlay,
    DriftDetector,
    IGIGitOps,
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
