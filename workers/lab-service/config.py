"""The Lab — configuration (Lead AI: The Dr. & Slime)"""

from __future__ import annotations

import os
import warnings

WORKER_NAME = "lab-service"
WORKER_PORT = int(os.environ.get("LAB_PORT", "8066"))
DB_PATH = os.environ.get("LAB_DB_PATH", "/data/lab.db")

# ── Code AI backend endpoints (all free/self-hosted) ──────────────────────────
# Primary: Ollama (local, zero-cost)
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_CODE_MODEL = os.environ.get("OLLAMA_CODE_MODEL", "deepseek-coder-v2:16b")
OLLAMA_FALLBACK_MODEL = os.environ.get("OLLAMA_FALLBACK_MODEL", "codellama:13b")
OLLAMA_FALLBACK2_MODEL = os.environ.get("OLLAMA_FALLBACK2_MODEL", "qwen2.5-coder:7b")

# Secondary: Tabby (self-hosted completion server, Apache 2.0)
TABBY_URL = os.environ.get("TABBY_URL", "http://tabby:8080")

# Tertiary: HuggingFace Inference API (free tier, rate-limited)
HF_API_KEY = os.environ.get("HF_API_KEY", "")
HF_CODE_MODEL = os.environ.get("HF_CODE_MODEL", "bigcode/starcoder2-7b")

# Quaternary: OpenRouter free code models (cloud, rate-limited)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_CODE_MODEL = os.environ.get("OPENROUTER_CODE_MODEL", "deepseek/deepseek-coder:free")

# ── ACO / ThresholdGuard ───────────────────────────────────────────────────────
PHEROMONE_DECAY = float(os.environ.get("LAB_PHEROMONE_DECAY", "0.05"))
QUOTA_WINDOW_SECONDS = int(os.environ.get("LAB_QUOTA_WINDOW", "3600"))
QUOTA_MAX_CALLS = int(os.environ.get("LAB_QUOTA_MAX_CALLS", "10000"))
# Hard stops for rate-limited cloud backends
HF_HOURLY_LIMIT = int(os.environ.get("LAB_HF_HOURLY_LIMIT", "300"))
OPENROUTER_HOURLY_LIMIT = int(os.environ.get("LAB_OPENROUTER_HOURLY_LIMIT", "200"))
PROBE_TIMEOUT = float(os.environ.get("LAB_PROBE_TIMEOUT", "5.0"))

# ── Continue.dev / Cline / Aider compatibility ────────────────────────────────
# These tools connect directly to Ollama's OpenAI-compatible endpoint:
# http://ollama:11434/v1  (no auth needed for self-hosted)
OPENAI_COMPAT_URL = os.environ.get("LAB_OPENAI_COMPAT_URL", f"{OLLAMA_URL}/v1")

# ── Internal auth ──────────────────────────────────────────────────────────────
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")
if not INTERNAL_SECRET:
    warnings.warn("INTERNAL_SECRET is not set — inter-service auth disabled", stacklevel=1)

# ── TLS ───────────────────────────────────────────────────────────────────────
TLS_VERIFY = os.environ.get("LAB_TLS_VERIFY", "0") != "0"

OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
