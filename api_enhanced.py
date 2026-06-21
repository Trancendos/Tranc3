"""DEPRECATED: Routes migrated to src/routers/enhanced_capabilities.py and included in api.py. Import from api.py."""

from __future__ import annotations

from collections import defaultdict

from api import app  # noqa: F401 — backward-compat re-export

# In-memory rate limiting store: maps client IP → request count.
# Populated by middleware in api.py; exposed here for test introspection.
_rate_store: dict = defaultdict(int)  # noqa: F841 — test introspection hook
