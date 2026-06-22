"""Cryptex / The Ice Box — configuration"""
from __future__ import annotations

import os

WORKER_NAME = "cryptex"
WORKER_PORT = int(os.environ.get("CRYPTEX_PORT", "8039"))
DB_PATH = os.environ.get("CRYPTEX_DB_PATH", "/data/cryptex.db")
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")

# ── Engine URLs ────────────────────────────────────────────────────────────────
WAZUH_URL = os.environ.get("WAZUH_URL", "http://wazuh-manager:55000")
WAZUH_USER = os.environ.get("WAZUH_USER", "wazuh-wui")
WAZUH_PASS = os.environ.get("WAZUH_PASS", "")

MISP_URL = os.environ.get("MISP_URL", "http://misp:80")
MISP_API_KEY = os.environ.get("MISP_API_KEY", "")

OPENVAS_URL = os.environ.get("OPENVAS_URL", "http://openvas:9390")
OPENVAS_USER = os.environ.get("OPENVAS_USER", "admin")
OPENVAS_PASS = os.environ.get("OPENVAS_PASS", "")

CLAMAV_SOCKET = os.environ.get("CLAMAV_SOCKET", "/tmp/clamd.sock")

SURICATA_LOG_DIR = os.environ.get("SURICATA_LOG_DIR", "/var/log/suricata")
YARA_RULES_DIR = os.environ.get("YARA_RULES_DIR", "/opt/yara-rules")

# ── ThresholdGuard ─────────────────────────────────────────────────────────────
THRESHOLD_WAZUH = int(os.environ.get("THRESHOLD_WAZUH", "500"))
THRESHOLD_MISP = int(os.environ.get("THRESHOLD_MISP", "500"))
THRESHOLD_OPENVAS = int(os.environ.get("THRESHOLD_OPENVAS", "100"))
THRESHOLD_CLAMAV = int(os.environ.get("THRESHOLD_CLAMAV", "1000"))
THRESHOLD_YARA = int(os.environ.get("THRESHOLD_YARA", "1000"))
THRESHOLD_SURICATA = int(os.environ.get("THRESHOLD_SURICATA", "500"))
THRESHOLD_SEMGREP = int(os.environ.get("THRESHOLD_SEMGREP", "200"))
THRESHOLD_WINDOW_SECONDS = int(os.environ.get("THRESHOLD_WINDOW_SECONDS", "3600"))

# ── ACO ────────────────────────────────────────────────────────────────────────
ACO_DECAY = float(os.environ.get("ACO_DECAY", "0.9"))
FORCE_ENGINE = os.environ.get("CRYPTEX_FORCE_ENGINE", "")
