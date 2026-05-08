# src/errors/error_catalog.py
# FID: TRANC3-ERR-001 | Version: 1.0.0 | Module: errors
# TRANC3 Error Catalog — structured error codes, messages, guidance, and self-healing actions

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Callable
import logging

logger = logging.getLogger(__name__)


# ── Error Code Taxonomy ───────────────────────────────────────────────────────
# Format: TRANC3-{DOMAIN}-{CODE}
# Domains: AUTH, RATE, MODEL, DB, QUANT, CONS, EVOL, SWARM, HOLO, SEC, COMP, SYS

class ErrorCode(str, Enum):
    # Auth
    AUTH_TOKEN_EXPIRED       = "TRANC3-AUTH-001"
    AUTH_TOKEN_INVALID       = "TRANC3-AUTH-002"
    AUTH_TOKEN_MISSING       = "TRANC3-AUTH-003"
    AUTH_USER_NOT_FOUND      = "TRANC3-AUTH-004"
    AUTH_WRONG_PASSWORD      = "TRANC3-AUTH-005"
    AUTH_ACCOUNT_DISABLED    = "TRANC3-AUTH-006"
    AUTH_WEAK_PASSWORD       = "TRANC3-AUTH-007"
    AUTH_USER_EXISTS         = "TRANC3-AUTH-008"

    # Rate limiting
    RATE_HOURLY_EXCEEDED     = "TRANC3-RATE-001"
    RATE_DAILY_EXCEEDED      = "TRANC3-RATE-002"
    RATE_TIER_INSUFFICIENT   = "TRANC3-RATE-003"

    # Model / Inference
    MODEL_NOT_LOADED         = "TRANC3-MODEL-001"
    MODEL_ECHO_MODE          = "TRANC3-MODEL-002"
    MODEL_INFERENCE_FAILED   = "TRANC3-MODEL-003"
    MODEL_LANGUAGE_UNSUPPORTED = "TRANC3-MODEL-004"
    MODEL_INPUT_TOO_LONG     = "TRANC3-MODEL-005"
    MODEL_TOKENIZER_FAILED   = "TRANC3-MODEL-006"

    # Database
    DB_CONNECTION_FAILED     = "TRANC3-DB-001"
    DB_WRITE_FAILED          = "TRANC3-DB-002"
    DB_READ_FAILED           = "TRANC3-DB-003"
    DB_MIGRATION_NEEDED      = "TRANC3-DB-004"

    # Quantum
    QUANT_BACKEND_FAILED     = "TRANC3-QUANT-001"
    QUANT_CIRCUIT_ERROR      = "TRANC3-QUANT-002"
    QUANT_FALLBACK_ACTIVE    = "TRANC3-QUANT-003"

    # Consciousness
    CONS_PHI_CALC_FAILED     = "TRANC3-CONS-001"
    CONS_ENGINE_UNAVAILABLE  = "TRANC3-CONS-002"

    # Evolution
    EVOL_NO_FEEDBACK         = "TRANC3-EVOL-001"
    EVOL_GENOME_CORRUPT      = "TRANC3-EVOL-002"

    # Swarm
    SWARM_NO_NODES           = "TRANC3-SWARM-001"
    SWARM_CONSENSUS_FAILED   = "TRANC3-SWARM-002"

    # Holographic
    HOLO_ENCODE_FAILED       = "TRANC3-HOLO-001"
    HOLO_RECALL_FAILED       = "TRANC3-HOLO-002"

    # Security
    SEC_INPUT_BLOCKED        = "TRANC3-SEC-001"
    SEC_CORS_VIOLATION       = "TRANC3-SEC-002"
    SEC_INTEGRITY_ALERT      = "TRANC3-SEC-003"
    SEC_IP_BLOCKED           = "TRANC3-SEC-004"

    # Compliance
    COMP_VIOLATION           = "TRANC3-COMP-001"
    COMP_GDPR_REQUIRED       = "TRANC3-COMP-002"

    # System
    SYS_REDIS_UNAVAILABLE    = "TRANC3-SYS-001"
    SYS_STARTUP_FAILED       = "TRANC3-SYS-002"
    SYS_UNKNOWN              = "TRANC3-SYS-999"


@dataclass
class ErrorDefinition:
    code:          ErrorCode
    http_status:   int
    title:         str
    message:       str
    guidance:      str           # Human-readable fix guidance
    docs_url:      str           # Link to knowledge base article
    self_heal:     Optional[str] = None   # Auto-remediation action name
    severity:      str           = "error"  # debug | info | warning | error | critical
    retryable:     bool          = False


# ── Error Catalog ─────────────────────────────────────────────────────────────
CATALOG: Dict[ErrorCode, ErrorDefinition] = {

    # Auth
    ErrorCode.AUTH_TOKEN_EXPIRED: ErrorDefinition(
        code=ErrorCode.AUTH_TOKEN_EXPIRED, http_status=401,
        title="Token Expired",
        message="Your authentication token has expired.",
        guidance="Call POST /auth/refresh with your current token to get a new one, or POST /auth/token to re-authenticate.",
        docs_url="/docs/errors/TRANC3-AUTH-001",
        retryable=True,
    ),
    ErrorCode.AUTH_TOKEN_INVALID: ErrorDefinition(
        code=ErrorCode.AUTH_TOKEN_INVALID, http_status=401,
        title="Invalid Token",
        message="The provided authentication token is malformed or has an invalid signature.",
        guidance="Ensure you are sending the token in the Authorization header as 'Bearer <token>'. Re-authenticate via POST /auth/token.",
        docs_url="/docs/errors/TRANC3-AUTH-002",
    ),
    ErrorCode.AUTH_WEAK_PASSWORD: ErrorDefinition(
        code=ErrorCode.AUTH_WEAK_PASSWORD, http_status=400,
        title="Password Too Weak",
        message="Password does not meet security requirements.",
        guidance="Password must be at least 8 characters and contain: one uppercase letter, one number.",
        docs_url="/docs/errors/TRANC3-AUTH-007",
    ),
    ErrorCode.AUTH_USER_EXISTS: ErrorDefinition(
        code=ErrorCode.AUTH_USER_EXISTS, http_status=400,
        title="Username Already Exists",
        message="A user with this username already exists.",
        guidance="Choose a different username or use POST /auth/token to sign in.",
        docs_url="/docs/errors/TRANC3-AUTH-008",
    ),

    # Rate
    ErrorCode.RATE_HOURLY_EXCEEDED: ErrorDefinition(
        code=ErrorCode.RATE_HOURLY_EXCEEDED, http_status=429,
        title="Hourly Rate Limit Exceeded",
        message="You have exceeded your hourly request limit.",
        guidance="Free tier: 100 req/hr. Upgrade to Pro (£29/mo) for 1,000 req/hr via POST /billing/checkout?tier=pro. Retry after the window resets.",
        docs_url="/docs/errors/TRANC3-RATE-001",
        retryable=True,
        self_heal="show_upgrade_prompt",
    ),
    ErrorCode.RATE_DAILY_EXCEEDED: ErrorDefinition(
        code=ErrorCode.RATE_DAILY_EXCEEDED, http_status=429,
        title="Daily Rate Limit Exceeded",
        message="You have exceeded your daily request limit.",
        guidance="Upgrade your tier or wait until midnight UTC for the daily window to reset.",
        docs_url="/docs/errors/TRANC3-RATE-002",
        retryable=True,
        self_heal="show_upgrade_prompt",
    ),

    # Model
    ErrorCode.MODEL_NOT_LOADED: ErrorDefinition(
        code=ErrorCode.MODEL_NOT_LOADED, http_status=503,
        title="Model Not Loaded",
        message="The AI model is not currently loaded.",
        guidance="The service is starting up or model weights are missing. Check MODEL_PATH in .env. Run 'make download-model' to get base weights.",
        docs_url="/docs/errors/TRANC3-MODEL-001",
        self_heal="attempt_model_reload",
        severity="critical",
        retryable=True,
    ),
    ErrorCode.MODEL_ECHO_MODE: ErrorDefinition(
        code=ErrorCode.MODEL_ECHO_MODE, http_status=200,
        title="Echo Mode Active",
        message="No model weights found — responses are echoed back.",
        guidance="Run 'python train.py' or 'make download-model' to get real model weights. Set MODEL_PATH in .env.",
        docs_url="/docs/errors/TRANC3-MODEL-002",
        severity="warning",
    ),
    ErrorCode.MODEL_LANGUAGE_UNSUPPORTED: ErrorDefinition(
        code=ErrorCode.MODEL_LANGUAGE_UNSUPPORTED, http_status=400,
        title="Language Not Supported",
        message="The requested language is not supported.",
        guidance="Call GET /languages to see the full list of supported language codes.",
        docs_url="/docs/errors/TRANC3-MODEL-004",
    ),

    # Database
    ErrorCode.DB_CONNECTION_FAILED: ErrorDefinition(
        code=ErrorCode.DB_CONNECTION_FAILED, http_status=503,
        title="Database Connection Failed",
        message="Cannot connect to the database.",
        guidance="Check DATABASE_URL in .env. For local dev, SQLite is used automatically. For production, set up Supabase and run 'make migrate'.",
        docs_url="/docs/errors/TRANC3-DB-001",
        self_heal="use_sqlite_fallback",
        severity="critical",
        retryable=True,
    ),
    ErrorCode.DB_MIGRATION_NEEDED: ErrorDefinition(
        code=ErrorCode.DB_MIGRATION_NEEDED, http_status=503,
        title="Database Migration Required",
        message="Database schema is out of date.",
        guidance="Run 'make migrate' or 'alembic upgrade head' to apply pending migrations.",
        docs_url="/docs/errors/TRANC3-DB-004",
        self_heal="run_migrations",
        severity="critical",
    ),

    # Quantum
    ErrorCode.QUANT_FALLBACK_ACTIVE: ErrorDefinition(
        code=ErrorCode.QUANT_FALLBACK_ACTIVE, http_status=200,
        title="Quantum Fallback Active",
        message="Quantum processing failed — classical fallback is active.",
        guidance="This is expected in environments without qiskit-aer. Enable ENABLE_QUANTUM_OPT=true and ensure qiskit-aer is installed.",
        docs_url="/docs/errors/TRANC3-QUANT-003",
        severity="warning",
    ),

    # Security
    ErrorCode.SEC_INPUT_BLOCKED: ErrorDefinition(
        code=ErrorCode.SEC_INPUT_BLOCKED, http_status=400,
        title="Input Blocked",
        message="Your message contains content that was blocked by the security filter.",
        guidance="Remove any script tags, SQL commands, or path traversal sequences from your message.",
        docs_url="/docs/errors/TRANC3-SEC-001",
        severity="warning",
    ),
    ErrorCode.SEC_INTEGRITY_ALERT: ErrorDefinition(
        code=ErrorCode.SEC_INTEGRITY_ALERT, http_status=500,
        title="File Integrity Alert",
        message="A platform file has failed integrity verification.",
        guidance="A file may have been tampered with. Contact your system administrator immediately. Check the registry via GET /admin/registry.",
        docs_url="/docs/errors/TRANC3-SEC-003",
        severity="critical",
    ),

    # System
    ErrorCode.SYS_REDIS_UNAVAILABLE: ErrorDefinition(
        code=ErrorCode.SYS_REDIS_UNAVAILABLE, http_status=200,
        title="Redis Unavailable",
        message="Redis is not available — feature flags and caching are disabled.",
        guidance="Set REDIS_URL in .env. For zero-cost: use Upstash Redis free tier. Feature flags will default to environment variables.",
        docs_url="/docs/errors/TRANC3-SYS-001",
        self_heal="use_env_feature_flags",
        severity="warning",
        retryable=True,
    ),
    ErrorCode.SYS_UNKNOWN: ErrorDefinition(
        code=ErrorCode.SYS_UNKNOWN, http_status=500,
        title="Internal Server Error",
        message="An unexpected error occurred.",
        guidance="Check the application logs for details. If this persists, check GET /health for component status.",
        docs_url="/docs/errors/TRANC3-SYS-999",
        severity="error",
    ),
}


def get_error(code: ErrorCode) -> ErrorDefinition:
    return CATALOG.get(code, CATALOG[ErrorCode.SYS_UNKNOWN])


def format_error_response(code: ErrorCode, detail: Optional[str] = None) -> Dict:
    defn = get_error(code)
    return {
        "error": {
            "code":      code.value,
            "title":     defn.title,
            "message":   detail or defn.message,
            "guidance":  defn.guidance,
            "docs_url":  defn.docs_url,
            "retryable": defn.retryable,
            "severity":  defn.severity,
        }
    }
