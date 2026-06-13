"""
shared_core — Trancendos Platform shared infrastructure layer.

Provides cross-cutting concerns used by all 38+ self-hosted workers:
- Error handlers and canonical error catalog integration
- Log sanitization (PII/secret scrubbing)
- Middleware (request logging, trace propagation)
- Models (shared Pydantic schemas)
- Orchestration utilities
- Security automation (watchdog)
- Architecture primitives (audit ledger, sentinel)
"""
