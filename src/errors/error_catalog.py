# src/errors/error_catalog.py
# FID: TRANC3-ERR-001 | Version: 1.0.0 | Module: errors
# TRANC3 Error Catalog — structured error codes, messages, guidance, and self-healing actions

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# ── Error Code Taxonomy ───────────────────────────────────────────────────────
# Format: TRANC3-{DOMAIN}-{CODE}
# Domains: AUTH, RATE, MODEL, DB, QUANT, CONS, EVOL, SWARM, HOLO, SEC, COMP, SYS


class ErrorCode(str, Enum):
    # Auth
    AUTH_TOKEN_EXPIRED = "TRANC3-AUTH-001"  # nosec B105 — false positive: not a password

    AUTH_TOKEN_INVALID = "TRANC3-AUTH-002"  # nosec B105 — false positive: not a password

    AUTH_TOKEN_MISSING = "TRANC3-AUTH-003"  # nosec B105 — false positive: not a password

    AUTH_USER_NOT_FOUND = "TRANC3-AUTH-004"
    AUTH_WRONG_PASSWORD = "TRANC3-AUTH-005"  # nosec B105 — false positive: not a password

    AUTH_ACCOUNT_DISABLED = "TRANC3-AUTH-006"
    AUTH_WEAK_PASSWORD = "TRANC3-AUTH-007"  # nosec B105 — false positive: not a password

    AUTH_USER_EXISTS = "TRANC3-AUTH-008"

    # Rate limiting
    RATE_HOURLY_EXCEEDED = "TRANC3-RATE-001"
    RATE_DAILY_EXCEEDED = "TRANC3-RATE-002"
    RATE_TIER_INSUFFICIENT = "TRANC3-RATE-003"

    # Model / Inference
    MODEL_NOT_LOADED = "TRANC3-MODEL-001"
    MODEL_ECHO_MODE = "TRANC3-MODEL-002"
    MODEL_INFERENCE_FAILED = "TRANC3-MODEL-003"
    MODEL_LANGUAGE_UNSUPPORTED = "TRANC3-MODEL-004"
    MODEL_INPUT_TOO_LONG = "TRANC3-MODEL-005"
    MODEL_TOKENIZER_FAILED = "TRANC3-MODEL-006"

    # Database
    DB_CONNECTION_FAILED = "TRANC3-DB-001"
    DB_WRITE_FAILED = "TRANC3-DB-002"
    DB_READ_FAILED = "TRANC3-DB-003"
    DB_MIGRATION_NEEDED = "TRANC3-DB-004"

    # Quantum
    QUANT_BACKEND_FAILED = "TRANC3-QUANT-001"
    QUANT_CIRCUIT_ERROR = "TRANC3-QUANT-002"
    QUANT_FALLBACK_ACTIVE = "TRANC3-QUANT-003"

    # Consciousness
    CONS_PHI_CALC_FAILED = "TRANC3-CONS-001"
    CONS_ENGINE_UNAVAILABLE = "TRANC3-CONS-002"

    # Evolution
    EVOL_NO_FEEDBACK = "TRANC3-EVOL-001"
    EVOL_GENOME_CORRUPT = "TRANC3-EVOL-002"

    # Swarm
    SWARM_NO_NODES = "TRANC3-SWARM-001"
    SWARM_CONSENSUS_FAILED = "TRANC3-SWARM-002"

    # Holographic
    HOLO_ENCODE_FAILED = "TRANC3-HOLO-001"
    HOLO_RECALL_FAILED = "TRANC3-HOLO-002"

    # Security
    SEC_INPUT_BLOCKED = "TRANC3-SEC-001"
    SEC_CORS_VIOLATION = "TRANC3-SEC-002"
    SEC_INTEGRITY_ALERT = "TRANC3-SEC-003"
    SEC_IP_BLOCKED = "TRANC3-SEC-004"

    # Compliance
    COMP_VIOLATION = "TRANC3-COMP-001"
    COMP_GDPR_REQUIRED = "TRANC3-COMP-002"

    # Workflow / The Digital Grid
    WF_NODE_FAILED = "TRANC3-WF-001"
    WF_CYCLE_DETECTED = "TRANC3-WF-002"
    WF_TIMEOUT = "TRANC3-WF-003"
    WF_INVALID_DAG = "TRANC3-WF-004"

    # Validation / Input
    VAL_SCHEMA_INVALID = "TRANC3-VAL-001"
    VAL_FIELD_REQUIRED = "TRANC3-VAL-002"
    VAL_FIELD_TOO_LONG = "TRANC3-VAL-003"
    VAL_INJECTION_DETECTED = "TRANC3-VAL-004"

    # Entity / Resource
    ENT_NOT_FOUND = "TRANC3-ENT-001"
    ENT_CONFLICT = "TRANC3-ENT-002"
    ENT_UNAVAILABLE = "TRANC3-ENT-003"
    ENT_ROTATION_FAILED = "TRANC3-ENT-004"

    # System
    SYS_REDIS_UNAVAILABLE = "TRANC3-SYS-001"
    SYS_STARTUP_FAILED = "TRANC3-SYS-002"
    SYS_UNKNOWN = "TRANC3-SYS-999"


@dataclass
class ErrorDefinition:
    code: ErrorCode
    http_status: int
    title: str
    message: str
    guidance: str  # Human-readable fix guidance
    docs_url: str  # Link to knowledge base article
    self_heal: Optional[str] = None  # Auto-remediation action name
    severity: str = "error"  # debug | info | warning | error | critical
    retryable: bool = False


# ── Error Catalog ─────────────────────────────────────────────────────────────
CATALOG: Dict[ErrorCode, ErrorDefinition] = {
    # Auth
    ErrorCode.AUTH_TOKEN_EXPIRED: ErrorDefinition(
        code=ErrorCode.AUTH_TOKEN_EXPIRED,
        http_status=401,
        title="Token Expired",
        message="Your authentication token has expired.",
        guidance="Call POST /auth/refresh with your current token to get a new one, or POST /auth/token to re-authenticate.",
        docs_url="/docs/errors/TRANC3-AUTH-001",
        retryable=True,
    ),
    ErrorCode.AUTH_TOKEN_INVALID: ErrorDefinition(
        code=ErrorCode.AUTH_TOKEN_INVALID,
        http_status=401,
        title="Invalid Token",
        message="The provided authentication token is malformed or has an invalid signature.",
        guidance="Ensure you are sending the token in the Authorization header as 'Bearer <token>'. Re-authenticate via POST /auth/token.",
        docs_url="/docs/errors/TRANC3-AUTH-002",
    ),
    ErrorCode.AUTH_TOKEN_MISSING: ErrorDefinition(
        code=ErrorCode.AUTH_TOKEN_MISSING,
        http_status=401,
        title="Token Missing",
        message="No authentication token was provided.",
        guidance="Include the token in the Authorization header as 'Bearer <token>'. Obtain a token via POST /auth/token.",
        docs_url="/docs/errors/TRANC3-AUTH-003",
    ),
    ErrorCode.AUTH_USER_NOT_FOUND: ErrorDefinition(
        code=ErrorCode.AUTH_USER_NOT_FOUND,
        http_status=404,
        title="User Not Found",
        message="No account exists with the provided username.",
        guidance="Check the username spelling or register a new account via POST /auth/register.",
        docs_url="/docs/errors/TRANC3-AUTH-004",
    ),
    ErrorCode.AUTH_WRONG_PASSWORD: ErrorDefinition(
        code=ErrorCode.AUTH_WRONG_PASSWORD,
        http_status=401,
        title="Wrong Password",
        message="The provided password is incorrect.",
        guidance="Check your password and try again. Use POST /auth/reset to initiate a password reset.",
        docs_url="/docs/errors/TRANC3-AUTH-005",
    ),
    ErrorCode.AUTH_ACCOUNT_DISABLED: ErrorDefinition(
        code=ErrorCode.AUTH_ACCOUNT_DISABLED,
        http_status=403,
        title="Account Disabled",
        message="This account has been disabled.",
        guidance="Contact your administrator to re-enable the account.",
        docs_url="/docs/errors/TRANC3-AUTH-006",
        severity="warning",
    ),
    ErrorCode.AUTH_WEAK_PASSWORD: ErrorDefinition(
        code=ErrorCode.AUTH_WEAK_PASSWORD,
        http_status=400,
        title="Password Too Weak",
        message="Password does not meet security requirements.",
        guidance="Password must be at least 8 characters and contain: one uppercase letter, one number.",
        docs_url="/docs/errors/TRANC3-AUTH-007",
    ),
    ErrorCode.AUTH_USER_EXISTS: ErrorDefinition(
        code=ErrorCode.AUTH_USER_EXISTS,
        http_status=400,
        title="Username Already Exists",
        message="A user with this username already exists.",
        guidance="Choose a different username or use POST /auth/token to sign in.",
        docs_url="/docs/errors/TRANC3-AUTH-008",
    ),
    # Rate
    ErrorCode.RATE_HOURLY_EXCEEDED: ErrorDefinition(
        code=ErrorCode.RATE_HOURLY_EXCEEDED,
        http_status=429,
        title="Hourly Rate Limit Exceeded",
        message="You have exceeded your hourly request limit.",
        guidance="Free tier: 100 req/hr. Upgrade to Pro (£29/mo) for 1,000 req/hr via POST /billing/checkout?tier=pro. Retry after the window resets.",
        docs_url="/docs/errors/TRANC3-RATE-001",
        retryable=True,
        self_heal="show_upgrade_prompt",
    ),
    ErrorCode.RATE_DAILY_EXCEEDED: ErrorDefinition(
        code=ErrorCode.RATE_DAILY_EXCEEDED,
        http_status=429,
        title="Daily Rate Limit Exceeded",
        message="You have exceeded your daily request limit.",
        guidance="Upgrade your tier or wait until midnight UTC for the daily window to reset.",
        docs_url="/docs/errors/TRANC3-RATE-002",
        retryable=True,
        self_heal="show_upgrade_prompt",
    ),
    ErrorCode.RATE_TIER_INSUFFICIENT: ErrorDefinition(
        code=ErrorCode.RATE_TIER_INSUFFICIENT,
        http_status=403,
        title="Tier Insufficient",
        message="This feature requires a higher subscription tier.",
        guidance="Upgrade via POST /billing/checkout. See GET /billing/tiers for available plans.",
        docs_url="/docs/errors/TRANC3-RATE-003",
        self_heal="show_upgrade_prompt",
        severity="warning",
    ),
    # Model
    ErrorCode.MODEL_NOT_LOADED: ErrorDefinition(
        code=ErrorCode.MODEL_NOT_LOADED,
        http_status=503,
        title="Model Not Loaded",
        message="The AI model is not currently loaded.",
        guidance="The service is starting up or model weights are missing. Check MODEL_PATH in .env. Run 'make download-model' to get base weights.",
        docs_url="/docs/errors/TRANC3-MODEL-001",
        self_heal="attempt_model_reload",
        severity="critical",
        retryable=True,
    ),
    ErrorCode.MODEL_ECHO_MODE: ErrorDefinition(
        code=ErrorCode.MODEL_ECHO_MODE,
        http_status=200,
        title="Echo Mode Active",
        message="No model weights found — responses are echoed back.",
        guidance="Run 'python train.py' or 'make download-model' to get real model weights. Set MODEL_PATH in .env.",
        docs_url="/docs/errors/TRANC3-MODEL-002",
        severity="warning",
    ),
    ErrorCode.MODEL_INFERENCE_FAILED: ErrorDefinition(
        code=ErrorCode.MODEL_INFERENCE_FAILED,
        http_status=500,
        title="Inference Failed",
        message="The model encountered an error during inference.",
        guidance="Check that model weights are valid. Try restarting the service or re-running 'python train.py'.",
        docs_url="/docs/errors/TRANC3-MODEL-003",
        self_heal="attempt_model_reload",
        severity="error",
        retryable=True,
    ),
    ErrorCode.MODEL_LANGUAGE_UNSUPPORTED: ErrorDefinition(
        code=ErrorCode.MODEL_LANGUAGE_UNSUPPORTED,
        http_status=400,
        title="Language Not Supported",
        message="The requested language is not supported.",
        guidance="Call GET /languages to see the full list of supported language codes.",
        docs_url="/docs/errors/TRANC3-MODEL-004",
    ),
    ErrorCode.MODEL_INPUT_TOO_LONG: ErrorDefinition(
        code=ErrorCode.MODEL_INPUT_TOO_LONG,
        http_status=400,
        title="Input Too Long",
        message="The input exceeds the maximum allowed token length.",
        guidance="Shorten your prompt or split it into smaller requests. Max context is defined by the model config.",
        docs_url="/docs/errors/TRANC3-MODEL-005",
    ),
    ErrorCode.MODEL_TOKENIZER_FAILED: ErrorDefinition(
        code=ErrorCode.MODEL_TOKENIZER_FAILED,
        http_status=500,
        title="Tokenizer Failed",
        message="The tokenizer could not process the input.",
        guidance="Ensure TRANC3_TOKENIZER_PATH is set and the tokenizer files exist. Run 'python train.py' to rebuild.",
        docs_url="/docs/errors/TRANC3-MODEL-006",
        severity="error",
        retryable=True,
    ),
    # Database
    ErrorCode.DB_CONNECTION_FAILED: ErrorDefinition(
        code=ErrorCode.DB_CONNECTION_FAILED,
        http_status=503,
        title="Database Connection Failed",
        message="Cannot connect to the database.",
        guidance="Check DATABASE_URL in .env. For local dev, SQLite is used automatically. For production, set up Supabase and run 'make migrate'.",
        docs_url="/docs/errors/TRANC3-DB-001",
        self_heal="use_sqlite_fallback",
        severity="critical",
        retryable=True,
    ),
    ErrorCode.DB_WRITE_FAILED: ErrorDefinition(
        code=ErrorCode.DB_WRITE_FAILED,
        http_status=503,
        title="Database Write Failed",
        message="Could not write data to the database.",
        guidance="Check database connectivity and disk space. See DATABASE_URL in .env.",
        docs_url="/docs/errors/TRANC3-DB-002",
        severity="error",
        retryable=True,
    ),
    ErrorCode.DB_READ_FAILED: ErrorDefinition(
        code=ErrorCode.DB_READ_FAILED,
        http_status=503,
        title="Database Read Failed",
        message="Could not read data from the database.",
        guidance="Check database connectivity. Run 'make migrate' if schema is out of date.",
        docs_url="/docs/errors/TRANC3-DB-003",
        severity="error",
        retryable=True,
    ),
    ErrorCode.DB_MIGRATION_NEEDED: ErrorDefinition(
        code=ErrorCode.DB_MIGRATION_NEEDED,
        http_status=503,
        title="Database Migration Required",
        message="Database schema is out of date.",
        guidance="Run 'make migrate' or 'alembic upgrade head' to apply pending migrations.",
        docs_url="/docs/errors/TRANC3-DB-004",
        self_heal="run_migrations",
        severity="critical",
    ),
    # Quantum
    ErrorCode.QUANT_BACKEND_FAILED: ErrorDefinition(
        code=ErrorCode.QUANT_BACKEND_FAILED,
        http_status=503,
        title="Quantum Backend Failed",
        message="The quantum processing backend is unavailable.",
        guidance="Ensure qiskit-aer is installed and ENABLE_QUANTUM_OPT=true is set. Classical fallback is active.",
        docs_url="/docs/errors/TRANC3-QUANT-001",
        severity="warning",
        retryable=True,
    ),
    ErrorCode.QUANT_CIRCUIT_ERROR: ErrorDefinition(
        code=ErrorCode.QUANT_CIRCUIT_ERROR,
        http_status=500,
        title="Quantum Circuit Error",
        message="A quantum circuit failed to execute.",
        guidance="Check circuit parameters. Classical fallback will be used automatically.",
        docs_url="/docs/errors/TRANC3-QUANT-002",
        severity="warning",
        retryable=True,
    ),
    ErrorCode.QUANT_FALLBACK_ACTIVE: ErrorDefinition(
        code=ErrorCode.QUANT_FALLBACK_ACTIVE,
        http_status=200,
        title="Quantum Fallback Active",
        message="Quantum processing failed — classical fallback is active.",
        guidance="This is expected in environments without qiskit-aer. Enable ENABLE_QUANTUM_OPT=true and ensure qiskit-aer is installed.",
        docs_url="/docs/errors/TRANC3-QUANT-003",
        severity="warning",
    ),
    ErrorCode.CONS_PHI_CALC_FAILED: ErrorDefinition(
        code=ErrorCode.CONS_PHI_CALC_FAILED,
        http_status=500,
        title="Phi Calculation Failed",
        message="Integrated information (Φ) calculation failed.",
        guidance="This is non-fatal — the consciousness subsystem will use a default Φ value. Check scipy installation.",
        docs_url="/docs/errors/TRANC3-CONS-001",
        severity="warning",
        retryable=True,
    ),
    ErrorCode.CONS_ENGINE_UNAVAILABLE: ErrorDefinition(
        code=ErrorCode.CONS_ENGINE_UNAVAILABLE,
        http_status=503,
        title="Consciousness Engine Unavailable",
        message="The consciousness subsystem could not be initialised.",
        guidance="Check scipy and torch installations. The system will operate without consciousness features.",
        docs_url="/docs/errors/TRANC3-CONS-002",
        severity="warning",
    ),
    ErrorCode.EVOL_NO_FEEDBACK: ErrorDefinition(
        code=ErrorCode.EVOL_NO_FEEDBACK,
        http_status=400,
        title="No Feedback Data",
        message="Self-evolution requires feedback data to proceed.",
        guidance="Provide at least one feedback sample before triggering an evolution cycle.",
        docs_url="/docs/errors/TRANC3-EVOL-001",
        severity="warning",
    ),
    ErrorCode.EVOL_GENOME_CORRUPT: ErrorDefinition(
        code=ErrorCode.EVOL_GENOME_CORRUPT,
        http_status=500,
        title="Genome Corrupt",
        message="The evolution genome data is corrupt or unreadable.",
        guidance="Delete the genome checkpoint and restart evolution from scratch.",
        docs_url="/docs/errors/TRANC3-EVOL-002",
        severity="error",
    ),
    ErrorCode.SWARM_NO_NODES: ErrorDefinition(
        code=ErrorCode.SWARM_NO_NODES,
        http_status=503,
        title="No Swarm Nodes",
        message="No swarm intelligence nodes are available.",
        guidance="Ensure SWARM_ENABLED=true and at least one node is reachable on the configured ports.",
        docs_url="/docs/errors/TRANC3-SWARM-001",
        severity="warning",
        retryable=True,
    ),
    ErrorCode.SWARM_CONSENSUS_FAILED: ErrorDefinition(
        code=ErrorCode.SWARM_CONSENSUS_FAILED,
        http_status=503,
        title="Swarm Consensus Failed",
        message="Swarm nodes could not reach consensus.",
        guidance="Check network connectivity between nodes. Reduce consensus threshold or increase timeout.",
        docs_url="/docs/errors/TRANC3-SWARM-002",
        severity="error",
        retryable=True,
    ),
    ErrorCode.HOLO_ENCODE_FAILED: ErrorDefinition(
        code=ErrorCode.HOLO_ENCODE_FAILED,
        http_status=500,
        title="Holographic Encode Failed",
        message="Failed to encode data into holographic memory.",
        guidance="Check numpy/scipy FFT availability. The memory crystal will fall back to standard storage.",
        docs_url="/docs/errors/TRANC3-HOLO-001",
        severity="warning",
        retryable=True,
    ),
    ErrorCode.HOLO_RECALL_FAILED: ErrorDefinition(
        code=ErrorCode.HOLO_RECALL_FAILED,
        http_status=500,
        title="Holographic Recall Failed",
        message="Failed to retrieve data from holographic memory.",
        guidance="The memory pattern may be corrupted. Try re-encoding the experience.",
        docs_url="/docs/errors/TRANC3-HOLO-002",
        severity="warning",
        retryable=True,
    ),
    # Security
    ErrorCode.SEC_INPUT_BLOCKED: ErrorDefinition(
        code=ErrorCode.SEC_INPUT_BLOCKED,
        http_status=400,
        title="Input Blocked",
        message="Your message contains content that was blocked by the security filter.",
        guidance="Remove any script tags, SQL commands, or path traversal sequences from your message.",
        docs_url="/docs/errors/TRANC3-SEC-001",
        severity="warning",
    ),
    ErrorCode.SEC_CORS_VIOLATION: ErrorDefinition(
        code=ErrorCode.SEC_CORS_VIOLATION,
        http_status=403,
        title="CORS Violation",
        message="The request origin is not permitted.",
        guidance="Add the origin to ALLOWED_ORIGINS in .env. For local dev, set ALLOWED_ORIGINS=*.",
        docs_url="/docs/errors/TRANC3-SEC-002",
        severity="warning",
    ),
    ErrorCode.SEC_INTEGRITY_ALERT: ErrorDefinition(
        code=ErrorCode.SEC_INTEGRITY_ALERT,
        http_status=500,
        title="File Integrity Alert",
        message="A platform file has failed integrity verification.",
        guidance="A file may have been tampered with. Contact your system administrator immediately. Check the registry via GET /admin/registry.",
        docs_url="/docs/errors/TRANC3-SEC-003",
        severity="critical",
    ),
    ErrorCode.SEC_IP_BLOCKED: ErrorDefinition(
        code=ErrorCode.SEC_IP_BLOCKED,
        http_status=403,
        title="IP Address Blocked",
        message="Requests from your IP address are not permitted.",
        guidance="Contact your administrator if you believe this is an error.",
        docs_url="/docs/errors/TRANC3-SEC-004",
        severity="warning",
    ),
    ErrorCode.COMP_VIOLATION: ErrorDefinition(
        code=ErrorCode.COMP_VIOLATION,
        http_status=403,
        title="Compliance Violation",
        message="The request violates a compliance policy.",
        guidance="Review the applicable policy in the compliance documentation before retrying.",
        docs_url="/docs/errors/TRANC3-COMP-001",
        severity="error",
    ),
    ErrorCode.COMP_GDPR_REQUIRED: ErrorDefinition(
        code=ErrorCode.COMP_GDPR_REQUIRED,
        http_status=403,
        title="GDPR Consent Required",
        message="This action requires explicit GDPR consent.",
        guidance="Obtain user consent and include the consent token in the request headers.",
        docs_url="/docs/errors/TRANC3-COMP-002",
        severity="warning",
    ),
    # Workflow / The Digital Grid
    ErrorCode.WF_NODE_FAILED: ErrorDefinition(
        code=ErrorCode.WF_NODE_FAILED,
        http_status=500,
        title="Workflow Node Failed",
        message="A node in the workflow DAG raised an exception.",
        guidance="Check the node execution log in GET /workflow/{id}/log. Fix the node handler and re-run.",
        docs_url="/docs/errors/TRANC3-WF-001",
        severity="error",
        retryable=True,
    ),
    ErrorCode.WF_CYCLE_DETECTED: ErrorDefinition(
        code=ErrorCode.WF_CYCLE_DETECTED,
        http_status=422,
        title="Workflow Cycle Detected",
        message="The workflow DAG contains a cycle, which prevents topological execution.",
        guidance="Review the workflow edges and remove any circular dependencies. Use GET /workflow/{id}/visualise to inspect the DAG.",
        docs_url="/docs/errors/TRANC3-WF-002",
        severity="error",
    ),
    ErrorCode.WF_TIMEOUT: ErrorDefinition(
        code=ErrorCode.WF_TIMEOUT,
        http_status=504,
        title="Workflow Timeout",
        message="The workflow exceeded its maximum execution time.",
        guidance="Increase the timeout in the workflow config, or split the workflow into smaller sub-workflows.",
        docs_url="/docs/errors/TRANC3-WF-003",
        severity="error",
        retryable=True,
    ),
    ErrorCode.WF_INVALID_DAG: ErrorDefinition(
        code=ErrorCode.WF_INVALID_DAG,
        http_status=422,
        title="Invalid Workflow DAG",
        message="The workflow definition is not a valid directed acyclic graph.",
        guidance="Validate the workflow JSON/YAML against the schema at /docs/workflow-schema.json.",
        docs_url="/docs/errors/TRANC3-WF-004",
        severity="error",
    ),
    # Validation
    ErrorCode.VAL_SCHEMA_INVALID: ErrorDefinition(
        code=ErrorCode.VAL_SCHEMA_INVALID,
        http_status=422,
        title="Schema Validation Failed",
        message="The request body did not match the expected schema.",
        guidance="Check the response body for field-level details and correct the payload.",
        docs_url="/docs/errors/TRANC3-VAL-001",
        severity="warning",
    ),
    ErrorCode.VAL_FIELD_REQUIRED: ErrorDefinition(
        code=ErrorCode.VAL_FIELD_REQUIRED,
        http_status=422,
        title="Required Field Missing",
        message="One or more required fields were absent from the request.",
        guidance="Ensure all required fields are present. Refer to the API docs for the endpoint schema.",
        docs_url="/docs/errors/TRANC3-VAL-002",
        severity="warning",
    ),
    ErrorCode.VAL_FIELD_TOO_LONG: ErrorDefinition(
        code=ErrorCode.VAL_FIELD_TOO_LONG,
        http_status=422,
        title="Field Exceeds Maximum Length",
        message="One or more fields exceed the allowed character limit.",
        guidance="Reduce the length of the field value to the documented maximum.",
        docs_url="/docs/errors/TRANC3-VAL-003",
        severity="warning",
    ),
    ErrorCode.VAL_INJECTION_DETECTED: ErrorDefinition(
        code=ErrorCode.VAL_INJECTION_DETECTED,
        http_status=400,
        title="Injection Pattern Detected",
        message="The input contains disallowed patterns (XSS, SQLi, prompt injection).",
        guidance="Remove all HTML tags, SQL keywords, and prompt manipulation phrases from the input.",
        docs_url="/docs/errors/TRANC3-VAL-004",
        severity="error",
        self_heal="sanitize_input",
    ),
    # Entity
    ErrorCode.ENT_NOT_FOUND: ErrorDefinition(
        code=ErrorCode.ENT_NOT_FOUND,
        http_status=404,
        title="Entity Not Found",
        message="The requested Trancendos entity or resource does not exist.",
        guidance="Verify the entity name/ID using GET /platform/entities. Check the canonical entity list in PLATFORM_ENTITIES.md.",
        docs_url="/docs/errors/TRANC3-ENT-001",
        severity="warning",
    ),
    ErrorCode.ENT_CONFLICT: ErrorDefinition(
        code=ErrorCode.ENT_CONFLICT,
        http_status=409,
        title="Entity Conflict",
        message="A resource with this identifier already exists.",
        guidance="Use a different identifier, or update the existing resource with PATCH.",
        docs_url="/docs/errors/TRANC3-ENT-002",
        severity="warning",
    ),
    ErrorCode.ENT_UNAVAILABLE: ErrorDefinition(
        code=ErrorCode.ENT_UNAVAILABLE,
        http_status=503,
        title="Entity Unavailable",
        message="The Trancendos entity is currently offline or in maintenance mode.",
        guidance="Check GET /platform/entities/{name}/health. The entity rotation pool will attempt a failover automatically.",
        docs_url="/docs/errors/TRANC3-ENT-003",
        severity="error",
        retryable=True,
    ),
    ErrorCode.ENT_ROTATION_FAILED: ErrorDefinition(
        code=ErrorCode.ENT_ROTATION_FAILED,
        http_status=503,
        title="Entity Rotation Failed",
        message="All instances in the entity's rotation pool are unhealthy.",
        guidance="Check GET /platform/rotation/{entity} for pool health. Restart the failing workers or add pool instances.",
        docs_url="/docs/errors/TRANC3-ENT-004",
        severity="critical",
        retryable=True,
    ),
    # System
    ErrorCode.SYS_REDIS_UNAVAILABLE: ErrorDefinition(
        code=ErrorCode.SYS_REDIS_UNAVAILABLE,
        http_status=200,
        title="Redis Unavailable",
        message="Redis is not available — feature flags and caching are disabled.",
        guidance="Set REDIS_URL in .env. For zero-cost: use Upstash Redis free tier. Feature flags will default to environment variables.",
        docs_url="/docs/errors/TRANC3-SYS-001",
        self_heal="use_env_feature_flags",
        severity="warning",
        retryable=True,
    ),
    ErrorCode.SYS_STARTUP_FAILED: ErrorDefinition(
        code=ErrorCode.SYS_STARTUP_FAILED,
        http_status=503,
        title="Startup Failed",
        message="The system failed to start up correctly.",
        guidance="Check application logs for the failing component. Run the startup validator: 'python -c \"from src.core.startup_validator import validate_startup; validate_startup()\"'.",
        docs_url="/docs/errors/TRANC3-SYS-002",
        severity="critical",
    ),
    ErrorCode.SYS_UNKNOWN: ErrorDefinition(
        code=ErrorCode.SYS_UNKNOWN,
        http_status=500,
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
            "code": code.value,
            "title": defn.title,
            "message": detail or defn.message,
            "guidance": defn.guidance,
            "docs_url": defn.docs_url,
            "retryable": defn.retryable,
            "severity": defn.severity,
        },
    }


# Flat dict alias used by compliance tests: code_str -> {guidance, http_status, ...}
ERROR_DEFINITIONS: Dict[str, Dict] = {
    code.value: {
        "guidance": defn.guidance,
        "action": defn.self_heal,
        "http_status": defn.http_status,
        "severity": defn.severity,
        "retryable": defn.retryable,
        "title": defn.title,
    }
    for code, defn in CATALOG.items()
}
