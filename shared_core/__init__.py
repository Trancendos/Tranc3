"""
shared_core — COMPATIBILITY SHIM
==================================
`shared_core` and `Dimensional` are the same thing.
Canonical name: **Dimensional**

This package re-exports everything from Dimensional so that any existing
import of `shared_core.*` continues to work while the codebase migrates
to the canonical `Dimensional.*` import paths.

New code should import from `Dimensional` directly.
"""

# Re-export top-level Dimensional symbols
# Expose sub-packages
from Dimensional import (  # noqa: F401  # noqa: F401
    bus,
    dimensionals,
    error_handlers,
    hive,
    infinity,
    log_sanitize,
    middleware,
    models,
    optional_import,
    orchestration,
    path_validation,
    registry,
    sanitize,
    security,
    security_automation,
    url_validation,
)

CANONICAL_NAME = "Dimensional"
