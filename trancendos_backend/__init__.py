"""
Trancendos-Backend — Platform Infrastructure Layer
====================================================
Houses everything that is NOT:
  - AI/ML (→ belongs in Tranc3 / Trance-One / T2ance)
  - A Dimensional shared-core service (→ belongs in Dimensional/)
  - A platform entity (→ belongs in src/entities/locations/<entity>/)

Trancendos-Backend responsibilities:
  - Database models and Alembic migrations (src/database/)
  - Billing and monetisation (src/monetisation/)
  - HTTP routers and API entrypoints (src/routers/, api.py)
  - Configuration management (src/config/)
  - Error catalog (src/errors/)
  - Registry (src/registry/)
  - Protocol definitions (src/protocols/)
  - Analytics pipeline (src/analytics/)
  - Admin OS operations (src/admin_os/)
  - Nanoservices proxy layer (src/nanoservices/)
  - Cloud cost optimiser (src/cloud/)
  - Compliance (src/compliance/)

Architecture note:
  This is the glue layer. It wires together Tier 1–5 AI packages,
  Dimensional shared services, and entity location modules into the
  deployable FastAPI application (api.py).
"""

LAYER = "trancendos-backend"
VERSION = "1.0.0"
