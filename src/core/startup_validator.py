# src/core/startup_validator.py
# Validates required env vars and configuration at startup.
# Raises RuntimeError for hard requirements; logs warnings for soft ones.

import logging
import os
import secrets

logger = logging.getLogger(__name__)

_ENV = os.getenv("ENVIRONMENT", "development")
_IS_PROD = _ENV == "production"


def _current_env() -> str:
    """Read ENVIRONMENT dynamically so tests and reloads see current config."""
    return os.getenv("ENVIRONMENT", _ENV).lower()


def _is_production() -> bool:
    return _IS_PROD or _current_env() == "production"


def validate_startup() -> None:
    """
    Run all startup checks. Call once from the FastAPI lifespan before
    initialising subsystems.
    """
    _check_secret_key()
    _check_jwt_secret()
    _check_database_url()
    _check_redis_url()
    _check_cors_origins()
    _check_api_key()
    _warn_optional()
    logger.info("Startup validation passed (environment=%s)", _current_env())


def _check_secret_key() -> None:
    secret = os.getenv("SECRET_KEY", "")
    if not secret:
        if _is_production():
            raise RuntimeError(
                "SECRET_KEY is not set. Set a strong random secret before deploying to production."
            )
        generated = secrets.token_hex(32)
        os.environ["SECRET_KEY"] = generated
        logger.warning(
            "SECRET_KEY not set — generated ephemeral key %s...  "
            "Set SECRET_KEY in .env for persistent signing.",
            generated[:8],
        )
    elif len(secret) < 32:
        msg = "SECRET_KEY is too short (< 32 chars). Use secrets.token_hex(32)."
        if _is_production():
            raise RuntimeError(msg)
        logger.warning(msg)


def _check_jwt_secret() -> None:
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        if _is_production():
            raise RuntimeError(
                "JWT_SECRET is not set. Set a strong random secret before deploying to production."
            )
        # Dev: generate a random one per process (tokens won't survive restarts).
        generated = secrets.token_hex(32)
        os.environ["JWT_SECRET"] = generated
        logger.warning(
            "JWT_SECRET not set — generated ephemeral secret %s...  "
            "Tokens will be invalid after restart. Set JWT_SECRET in .env.",
            generated[:8],
        )
    elif len(secret) < 32:
        msg = "JWT_SECRET is too short (< 32 chars). Use secrets.token_hex(32)."
        if _is_production():
            raise RuntimeError(msg)
        logger.warning(msg)


def _check_database_url() -> None:
    if not os.getenv("DATABASE_URL"):
        if _is_production():
            raise RuntimeError("DATABASE_URL is required in production.")
        logger.warning("DATABASE_URL not set — database features will be unavailable.")


def _check_redis_url() -> None:
    if not os.getenv("REDIS_URL"):
        if _is_production():
            raise RuntimeError(
                "REDIS_URL is required in production (used for rate limiting and caching)."
            )
        logger.warning(
            "REDIS_URL not set — in-memory rate limiting active. "
            "This does NOT persist across restarts or scale across replicas."
        )


def _check_cors_origins() -> None:
    origins = os.getenv("CORS_ORIGINS", os.getenv("ALLOWED_ORIGINS", ""))
    parsed = [origin.strip() for origin in origins.split(",") if origin.strip()]
    if _is_production() and (not parsed or "*" in parsed):
        raise RuntimeError(
            "CORS_ORIGINS must be set to specific domain(s) in production. "
            "Wildcard '*' is not acceptable."
        )


def _check_api_key() -> None:
    require_auth = os.getenv("REQUIRE_AUTH", "false").lower() == "true"
    if _is_production() and require_auth and not os.getenv("TRANC3_API_KEY"):
        raise RuntimeError("TRANC3_API_KEY must be set in production when REQUIRE_AUTH=true.")
    if require_auth and not os.getenv("TRANC3_API_KEY") and not os.getenv("JWT_SECRET"):
        logger.warning(
            "REQUIRE_AUTH=true but neither TRANC3_API_KEY nor JWT_SECRET is set — all requests will fail auth."
        )


def _warn_optional() -> None:
    optional = {
        "TRANC3_MODEL_PATH": "Custom model path not set — using default ./models/tranc3-v1/tranc3-final.pt",
        "TRANC3_TOKENIZER_PATH": "Custom tokenizer path not set — using default ./models/tokenizer",
        "PINECONE_API_KEY": "Pinecone vector search will be unavailable; falling back to local FAISS.",
        "STRIPE_SECRET_KEY": "Payments/billing endpoints will be unavailable.",  # nosec B105 — false positive: not a password
        "LANGFUSE_PUBLIC_KEY": "LLM observability via Langfuse will be inactive.",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "OpenTelemetry tracing will be inactive.",
    }
    for key, msg in optional.items():
        if not os.getenv(key):
            logger.info("Optional config %s not set — %s", key, msg)
