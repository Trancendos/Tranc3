# src/core/config.py
# Pydantic-settings based configuration with hot-reload support
# Replaces the scattered os.getenv() calls across the codebase

import os
from typing import List, Optional

try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings  # type: ignore[no-redef]

from pydantic import Field, validator


class Tranc3Config(BaseSettings):
    """
    Centralized configuration for Tranc3 platform.
    All settings are loaded from environment variables with sensible defaults.
    """

    # ── Core ──────────────────────────────────────────────────────────────
    APP_NAME: str = "Tranc3 AI"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")

    # ── Security (required) ───────────────────────────────────────────────
    SECRET_KEY: str = Field(..., env="SECRET_KEY")  # No default — must be set
    JWT_SECRET: str = Field(..., env="JWT_SECRET")  # No default — must be set
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Model & Inference ─────────────────────────────────────────────────
    MODEL_PATH: str = Field(default="./models/tranc3-base.pt", env="MODEL_PATH")
    CACHE_DIR: str = Field(default="./cache", env="CACHE_DIR")
    VOCAB_SIZE: int = 119547
    HIDDEN_SIZE: int = 768
    INFERENCE_TIMEOUT: float = Field(default=30.0, env="INFERENCE_TIMEOUT")
    MAX_CONTEXT_LENGTH: int = Field(default=4096, env="MAX_CONTEXT_LENGTH")

    # ── LLM Router (zero-cost tier fallback) ─────────────────────────────
    LLM_PRIMARY_PROVIDER: str = Field(default="tranc3", env="LLM_PRIMARY_PROVIDER")
    LLM_FALLBACK_PROVIDERS: str = Field(
        default="ollama,openrouter,huggingface,stub",
        env="LLM_FALLBACK_PROVIDERS",
    )
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    OPENROUTER_API_KEY: Optional[str] = Field(default=None, env="OPENROUTER_API_KEY")
    HUGGINGFACE_API_KEY: Optional[str] = Field(default=None, env="HUGGINGFACE_API_KEY")

    # ── Database & Cache ──────────────────────────────────────────────────
    DATABASE_URL: str = Field(default="sqlite:///./tranc3.db", env="DATABASE_URL")
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")

    # ── Server ────────────────────────────────────────────────────────────
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8000, env="PORT")
    WORKERS: int = Field(default=1, env="WORKERS")
    CORS_ORIGINS: str = Field(default="*", env="CORS_ORIGINS")
    MAX_BODY_SIZE: int = Field(default=10 * 1024 * 1024, env="MAX_BODY_SIZE")  # 10MB

    # ── Feature Flags ─────────────────────────────────────────────────────
    ENABLE_EMOTION: bool = Field(default=True, env="ENABLE_EMOTION")
    ENABLE_QUANTUM: bool = Field(default=False, env="ENABLE_QUANTUM")
    ENABLE_EVOLUTION: bool = Field(default=True, env="ENABLE_EVOLUTION")
    ENABLE_CONSCIOUSNESS: bool = Field(default=True, env="ENABLE_CONSCIOUSNESS")
    ENABLE_BILLING: bool = Field(default=True, env="ENABLE_BILLING")

    # ── Languages ─────────────────────────────────────────────────────────
    PRIMARY_LANGUAGE: str = Field(default="en", env="PRIMARY_LANGUAGE")
    SUPPORTED_LANGUAGES: str = Field(
        default="en,es,fr,de,zh,ja", env="SUPPORTED_LANGUAGES"
    )

    # ── Personality ───────────────────────────────────────────────────────
    PERSONALITY_DIR: str = Field(
        default="./src/personality/profiles", env="PERSONALITY_DIR"
    )

    # ── Observability ─────────────────────────────────────────────────────
    LANGFUSE_PUBLIC_KEY: Optional[str] = Field(default=None, env="LANGFUSE_PUBLIC_KEY")
    LANGFUSE_SECRET_KEY: Optional[str] = Field(default=None, env="LANGFUSE_SECRET_KEY")
    LANGFUSE_HOST: str = Field(default="http://localhost:3000", env="LANGFUSE_HOST")

    # ── Nanoservice Mesh ──────────────────────────────────────────────────
    NANO_PORT: int = Field(default=8001, env="NANO_PORT")
    NANO_HEALTH_INTERVAL: float = Field(default=30.0, env="NANO_HEALTH_INTERVAL")

    @validator("LOG_LEVEL")
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}")
        return upper

    @validator("ENVIRONMENT")
    def validate_environment(cls, v: str) -> str:
        valid = {"development", "staging", "production"}
        lower = v.lower()
        if lower not in valid:
            raise ValueError(f"ENVIRONMENT must be one of {valid}")
        return lower

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def supported_languages_list(self) -> List[str]:
        return [l.strip() for l in self.SUPPORTED_LANGUAGES.split(",")]

    @property
    def fallback_providers_list(self) -> List[str]:
        return [p.strip() for p in self.LLM_FALLBACK_PROVIDERS.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Singleton — loaded once, importable everywhere
try:
    settings = Tranc3Config()
except Exception as e:
    import logging
    logging.getLogger(__name__).error(f"Configuration error: {e}")
    raise RuntimeError(
        f"Tranc3 configuration failed: {e}. "
        "Check your environment variables and .env file."
    ) from e