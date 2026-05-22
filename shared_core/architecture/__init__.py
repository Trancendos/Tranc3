"""
shared_core.architecture — Environment-aware architecture with smart services.

Implements the core architectural components that adapt to the deployment
environment (TRUE_NAS, HYBRID, CLOUD_ONLY) while maintaining the Zero-Cost
Mandate — all services use free tiers or self-hosted alternatives.

Components:
    StorageFactory   — Environment-aware storage provider pattern
    VaultSecretLoader — Secure secret loading with memory zeroization
    AuditLedger      — Append-only signed records for compliance
    Sentinel         — Continuous verification daemon
"""

from shared_core.architecture.storage_factory import StorageFactory, StorageProvider
from shared_core.architecture.vault import VaultSecretLoader
from shared_core.architecture.audit_ledger import AuditLedger, AuditRecord
from shared_core.architecture.sentinel import Sentinel

__all__ = [
    "StorageFactory",
    "StorageProvider",
    "VaultSecretLoader",
    "AuditLedger",
    "AuditRecord",
    "Sentinel",
]
