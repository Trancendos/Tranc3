"""The Library — configuration"""

from __future__ import annotations

import os

WORKER_NAME = "library-service"
WORKER_PORT = int(os.environ.get("LIBRARY_PORT", "8067"))
DB_PATH = os.environ.get("LIBRARY_DB_PATH", "/data/library.db")

# ── ACO backend endpoints ──────────────────────────────────────────────────────
# Primary: Outline (self-hosted wiki, MIT)
OUTLINE_URL = os.environ.get("OUTLINE_URL", "http://outline:3000")
OUTLINE_API_KEY = os.environ.get("OUTLINE_API_KEY", "")

# Secondary: BookStack (self-hosted wiki/docs, MIT)
BOOKSTACK_URL = os.environ.get("BOOKSTACK_URL", "http://bookstack:80")
BOOKSTACK_TOKEN_ID = os.environ.get("BOOKSTACK_TOKEN_ID", "")
BOOKSTACK_TOKEN_SECRET = os.environ.get("BOOKSTACK_TOKEN_SECRET", "")

# Tertiary: Wiki.js (self-hosted, AGPL)
WIKIJS_URL = os.environ.get("WIKIJS_URL", "http://wikijs:3000")
WIKIJS_API_KEY = os.environ.get("WIKIJS_API_KEY", "")

# Quaternary: Gollum (self-hosted Git wiki, MIT)
GOLLUM_URL = os.environ.get("GOLLUM_URL", "http://gollum:4567")

# Quinary: DokuWiki (self-hosted, GPL)
DOKUWIKI_URL = os.environ.get("DOKUWIKI_URL", "http://dokuwiki:80")
DOKUWIKI_USER = os.environ.get("DOKUWIKI_USER", "")
DOKUWIKI_PASS = os.environ.get("DOKUWIKI_PASS", "")

# Senary: MkDocs (static, MIT — built from local git)
MKDOCS_URL = os.environ.get("MKDOCS_URL", "http://mkdocs:8000")

# Septenary: Gitea Wiki (self-hosted, MIT)
GITEA_URL = os.environ.get("GITEA_URL", "http://gitea:3000")
GITEA_TOKEN = os.environ.get("GITEA_TOKEN", "")

# Octonary: TiddlyWiki (offline/node, BSD)
TIDDLYWIKI_URL = os.environ.get("TIDDLYWIKI_URL", "http://tiddlywiki:8080")

# ── ACO / ThresholdGuard ───────────────────────────────────────────────────────
PHEROMONE_DECAY = float(os.environ.get("LIBRARY_PHEROMONE_DECAY", "0.05"))
QUOTA_WINDOW_SECONDS = int(os.environ.get("LIBRARY_QUOTA_WINDOW", "3600"))
QUOTA_MAX_CALLS = int(os.environ.get("LIBRARY_QUOTA_MAX_CALLS", "5000"))
PROBE_TIMEOUT = float(os.environ.get("LIBRARY_PROBE_TIMEOUT", "5.0"))

# ── Internal auth ──────────────────────────────────────────────────────────────
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")
if not INTERNAL_SECRET:
    import warnings

    warnings.warn("INTERNAL_SECRET is not set — inter-service auth disabled", stacklevel=1)

# ── TLS ───────────────────────────────────────────────────────────────────────
TLS_VERIFY = os.environ.get("LIBRARY_TLS_VERIFY", "0") != "0"

OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
