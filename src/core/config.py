# src/core/config.py
# Pydantic-settings based configuration with hot-reload support
# Replaces the scattered os.getenv() calls across the codebase

from typing import List, Optional

from pydantic import ConfigDict, Field, field_validator

try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings  # type: ignore[no-redef]


class Tranc3Config(BaseSettings):
    """
    Centralized configuration for Tranc3 platform.
    All settings are loaded from environment variables with sensible defaults.
    In pydantic-settings V2, env vars are mapped automatically by field name.
    """

    # ── Core ──────────────────────────────────────────────────────────────
    APP_NAME: str = "Tranc3 AI"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = Field(default=False)
    LOG_LEVEL: str = Field(default="INFO")
    ENVIRONMENT: str = Field(default="development")

    # ── Security (required) ──────────────────────────────────────────────
    SECRET_KEY: str = Field(default="dev-secret-key-change-in-production")
    JWT_SECRET: str = Field(default="dev-jwt-secret-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Model & Inference ────────────────────────────────────────────────
    MODEL_PATH: str = Field(default="./models/tranc3-base.pt")
    CACHE_DIR: str = Field(default="./cache")
    VOCAB_SIZE: int = 119547
    HIDDEN_SIZE: int = 768
    INFERENCE_TIMEOUT: float = Field(default=30.0)
    MAX_CONTEXT_LENGTH: int = Field(default=4096)

    # ── LLM Router (zero-cost tier fallback) ─────────────────────────────
    LLM_PRIMARY_PROVIDER: str = Field(default="tranc3")
    LLM_FALLBACK_PROVIDERS: str = Field(
        default="ollama,openrouter,huggingface,stub",
    )
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434")
    OPENROUTER_API_KEY: Optional[str] = Field(default=None)
    HUGGINGFACE_API_KEY: Optional[str] = Field(default=None)

    # ── Database & Cache ─────────────────────────────────────────────────
    DATABASE_URL: str = Field(default="sqlite:///./tranc3.db")
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # ── Server ───────────────────────────────────────────────────────────
    HOST: str = Field(default="127.0.0.1")
    PORT: int = Field(default=8000)
    WORKERS: int = Field(default=1)
    CORS_ORIGINS: str = Field(default="*")
    MAX_BODY_SIZE: int = Field(default=10 * 1024 * 1024)  # 10MB

    # ── Feature Flags ────────────────────────────────────────────────────
    ENABLE_EMOTION: bool = Field(default=True)
    ENABLE_QUANTUM: bool = Field(default=False)
    ENABLE_EVOLUTION: bool = Field(default=True)
    ENABLE_CONSCIOUSNESS: bool = Field(default=True)
    ENABLE_BILLING: bool = Field(default=True)

    # ── Languages ────────────────────────────────────────────────────────
    PRIMARY_LANGUAGE: str = Field(default="en")
    SUPPORTED_LANGUAGES: str = Field(default="en,es,fr,de,zh,ja")

    # ── Personality ──────────────────────────────────────────────────────
    PERSONALITY_DIR: str = Field(default="./src/personality/profiles")

    # ── Observability ────────────────────────────────────────────────────
    LANGFUSE_PUBLIC_KEY: Optional[str] = Field(default=None)
    LANGFUSE_SECRET_KEY: Optional[str] = Field(default=None)
    LANGFUSE_HOST: str = Field(default="http://localhost:3000")

    # ── Nanoservice Mesh ─────────────────────────────────────────────────
    NANO_PORT: int = Field(default=8001)
    NANO_HEALTH_INTERVAL: float = Field(default=30.0)

    @field_validator("SECRET_KEY", mode="after")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if not v or not v.strip() or v == "dev-secret-key-change-in-production":
            raise ValueError(
                "SECRET_KEY must be set to a real secret. Set the SECRET_KEY environment variable."
            )
        return v

    @field_validator("JWT_SECRET", mode="after")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if not v or not v.strip() or v == "dev-jwt-secret-change-in-production":
            raise ValueError(
                "JWT_SECRET must be set to a real secret. Set the JWT_SECRET environment variable."
            )
        return v

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure LOG_LEVEL is one of the accepted severity names."""
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}")
        return upper

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Ensure ENVIRONMENT is one of the accepted deployment stages."""
        valid = {"development", "staging", "production"}
        lower = v.lower()
        if lower not in valid:
            raise ValueError(f"ENVIRONMENT must be one of {valid}")
        return lower

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS comma-separated string into a list."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def supported_languages_list(self) -> List[str]:
        """Parse SUPPORTED_LANGUAGES comma-separated string into a list."""
        return [lang.strip() for lang in self.SUPPORTED_LANGUAGES.split(",")]

    @property
    def fallback_providers_list(self) -> List[str]:
        """Parse LLM_FALLBACK_PROVIDERS comma-separated string into a list."""
        return [p.strip() for p in self.LLM_FALLBACK_PROVIDERS.split(",")]

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


# Singleton — loaded once, importable everywhere
try:
    settings = Tranc3Config()
except Exception as e:
    import logging

    logging.getLogger(__name__).error(f"Configuration error: {e}")
    raise RuntimeError(
        f"Tranc3 configuration failed: {e}. Check your environment variables and .env file.",
    ) from e
