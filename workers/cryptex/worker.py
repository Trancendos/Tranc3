"""
Cryptex / The Ice Box — Backwards-compatibility shim
======================================================
Modular structure:
    config.py   — env vars, engine URLs, thresholds
    database.py — CryptexDatabase SQLite class
    models.py   — Pydantic models, ScanEngine enum
    service.py  — 8-tier adaptive SecurityEngineRouter + ACO pheromone + ThresholdGuard
    router.py   — FastAPI routes via APIRouter
    main.py     — app factory + lifespan

Security Engines (ACO adaptive selection + waterfall fallback):
  Internal  : Local IOC SQLite lookup     (always available)
  Tier 1    : Wazuh SIEM/EDR             REST API  (port 55000)  — Cryptex
  Tier 2    : MISP Threat Intelligence   REST API  (port 80)     — Cryptex
  Tier 3    : OpenVAS/Greenbone          REST API  (port 9390)   — Cryptex
  Tier 4    : ClamAV Antivirus           clamd socket            — The Ice Box
  Tier 5    : YARA Rules Engine          in-process              — The Ice Box
  Tier 6    : Suricata IDS               log-file reader         — Cryptex
  Tier 7    : Semgrep SAST               subprocess CLI          — Cryptex
  Tier 8    : Offline stub               (always works)

Lead AIs: Renik (Cryptex) + Neonach (The Ice Box)

Uvicorn deployments that reference ``worker:app`` continue to work.
"""

from main import app  # noqa: F401  re-exported for uvicorn worker:app

__all__ = ["app"]
