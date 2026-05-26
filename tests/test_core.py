# tests/test_core.py
# Tests for src/core/ modules: config, security, startup_validator

import importlib
import os
from unittest.mock import patch

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# Tranc3Config (src/core/config.py)
# ═══════════════════════════════════════════════════════════════════════════════
#
# The config module has a module-level `settings = Tranc3Config()` that fails
# if SECRET_KEY/JWT_SECRET are missing or ENVIRONMENT is invalid. Other test
# modules (e.g. test_enhanced_api.py) set ENVIRONMENT=test which poisons the
# import. To work around this, we reload the module with clean env vars each
# time, and never rely on the cached import.
# ═══════════════════════════════════════════════════════════════════════════════


def _make_config(**overrides):
    """Build a Tranc3Config with required env vars set and optional overrides.

    Reloads src.core.config from scratch to avoid poisoned module cache.
    """
    env = {
        "SECRET_KEY": "a" * 32,
        "JWT_SECRET": "b" * 32,
        "ENVIRONMENT": "development",
    }
    env.update(overrides)
    with patch.dict(os.environ, env, clear=False):
        import src.core.config as cfg_mod

        importlib.reload(cfg_mod)
        return cfg_mod.Tranc3Config()


class TestTranc3Config:
    """Tests for the Tranc3Config pydantic-settings model."""

    # ── defaults ────────────────────────────────────────────────────────────

    def test_default_app_name(self):
        cfg = _make_config()
        assert cfg.APP_NAME == "Tranc3 AI"

    def test_default_app_version(self):
        cfg = _make_config()
        assert cfg.APP_VERSION == "0.1.0"

    def test_default_debug_false(self):
        cfg = _make_config()
        assert cfg.DEBUG is False

    def test_default_log_level(self):
        cfg = _make_config()
        assert cfg.LOG_LEVEL == "INFO"

    def test_default_environment(self):
        cfg = _make_config()
        assert cfg.ENVIRONMENT == "development"

    def test_default_jwt_algorithm(self):
        cfg = _make_config()
        assert cfg.JWT_ALGORITHM == "HS256"

    def test_default_access_token_expire_minutes(self):
        cfg = _make_config()
        assert cfg.ACCESS_TOKEN_EXPIRE_MINUTES == 60

    def test_default_refresh_token_expire_days(self):
        cfg = _make_config()
        assert cfg.REFRESH_TOKEN_EXPIRE_DAYS == 30

    def test_default_model_path(self):
        cfg = _make_config()
        assert cfg.MODEL_PATH == "./models/tranc3-base.pt"

    def test_default_cache_dir(self):
        cfg = _make_config()
        assert cfg.CACHE_DIR == "./cache"

    def test_default_vocab_size(self):
        cfg = _make_config()
        assert cfg.VOCAB_SIZE == 119547

    def test_default_hidden_size(self):
        cfg = _make_config()
        assert cfg.HIDDEN_SIZE == 768

    def test_default_inference_timeout(self):
        cfg = _make_config()
        assert cfg.INFERENCE_TIMEOUT == 30.0

    def test_default_max_context_length(self):
        cfg = _make_config()
        assert cfg.MAX_CONTEXT_LENGTH == 4096

    def test_default_llm_primary_provider(self):
        cfg = _make_config()
        assert cfg.LLM_PRIMARY_PROVIDER == "tranc3"

    def test_default_llm_fallback_providers(self):
        cfg = _make_config()
        assert "ollama" in cfg.LLM_FALLBACK_PROVIDERS

    def test_default_database_url(self):
        cfg = _make_config()
        assert "sqlite" in cfg.DATABASE_URL

    def test_default_redis_url(self):
        cfg = _make_config()
        assert "redis" in cfg.REDIS_URL

    def test_default_host(self):
        cfg = _make_config()
        assert cfg.HOST == "127.0.0.1"

    def test_default_port(self):
        cfg = _make_config()
        assert cfg.PORT == 8000

    def test_default_cors_origins(self):
        cfg = _make_config()
        assert cfg.CORS_ORIGINS == "*"

    def test_default_feature_flags(self):
        cfg = _make_config()
        assert cfg.ENABLE_EMOTION is True
        assert cfg.ENABLE_QUANTUM is False
        assert cfg.ENABLE_EVOLUTION is True
        assert cfg.ENABLE_CONSCIOUSNESS is True
        assert cfg.ENABLE_BILLING is True

    def test_default_primary_language(self):
        cfg = _make_config()
        assert cfg.PRIMARY_LANGUAGE == "en"

    def test_default_supported_languages(self):
        cfg = _make_config()
        assert "en" in cfg.SUPPORTED_LANGUAGES
        assert "es" in cfg.SUPPORTED_LANGUAGES

    def test_default_nano_port(self):
        cfg = _make_config()
        assert cfg.NANO_PORT == 8001

    def test_default_nano_health_interval(self):
        cfg = _make_config()
        assert cfg.NANO_HEALTH_INTERVAL == 30.0

    # ── required fields ─────────────────────────────────────────────────────

    def test_missing_secret_key_raises(self):
        """Tranc3Config requires SECRET_KEY; without it, validation should fail."""
        from src.core.config import Tranc3Config

        env = {"JWT_SECRET": "b" * 32, "ENVIRONMENT": "development"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(Exception):
                Tranc3Config()

    def test_missing_jwt_secret_raises(self):
        """Tranc3Config requires JWT_SECRET; without it, validation should fail."""
        from src.core.config import Tranc3Config

        env = {"SECRET_KEY": "a" * 32, "ENVIRONMENT": "development"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(Exception):
                Tranc3Config()

    # ── env overrides ───────────────────────────────────────────────────────

    def test_debug_from_env(self):
        cfg = _make_config(DEBUG="true")
        assert cfg.DEBUG is True

    def test_port_from_env(self):
        cfg = _make_config(PORT="9000")
        assert cfg.PORT == 9000

    # ── LOG_LEVEL validator ─────────────────────────────────────────────────

    def test_log_level_uppercase(self):
        cfg = _make_config(LOG_LEVEL="warning")
        assert cfg.LOG_LEVEL == "WARNING"

    def test_log_level_valid_values(self):
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            cfg = _make_config(LOG_LEVEL=level)
            assert cfg.LOG_LEVEL == level

    def test_log_level_invalid_raises(self):
        with pytest.raises(Exception):
            _make_config(LOG_LEVEL="VERBOSE")

    # ── ENVIRONMENT validator ───────────────────────────────────────────────

    def test_environment_lowercase(self):
        cfg = _make_config(ENVIRONMENT="PRODUCTION")
        assert cfg.ENVIRONMENT == "production"

    def test_environment_valid_values(self):
        for env_name in ("development", "staging", "production"):
            cfg = _make_config(ENVIRONMENT=env_name)
            assert cfg.ENVIRONMENT == env_name

    def test_environment_invalid_raises(self):
        with pytest.raises(Exception):
            _make_config(ENVIRONMENT="testing")

    # ── computed properties ─────────────────────────────────────────────────

    def test_cors_origins_list(self):
        cfg = _make_config(CORS_ORIGINS="http://a.com, http://b.com")
        assert cfg.cors_origins_list == ["http://a.com", "http://b.com"]

    def test_cors_origins_list_wildcard(self):
        cfg = _make_config()
        assert cfg.cors_origins_list == ["*"]

    def test_supported_languages_list(self):
        cfg = _make_config(SUPPORTED_LANGUAGES="en, fr, de")
        assert cfg.supported_languages_list == ["en", "fr", "de"]

    def test_fallback_providers_list(self):
        cfg = _make_config(LLM_FALLBACK_PROVIDERS="ollama,openrouter,stub")
        assert cfg.fallback_providers_list == ["ollama", "openrouter", "stub"]

    # ── optional fields ─────────────────────────────────────────────────────

    def test_optional_api_keys_default_none(self):
        cfg = _make_config()
        assert cfg.OPENROUTER_API_KEY is None
        assert cfg.HUGGINGFACE_API_KEY is None

    def test_optional_observability_keys_default_none(self):
        cfg = _make_config()
        assert cfg.LANGFUSE_PUBLIC_KEY is None
        assert cfg.LANGFUSE_SECRET_KEY is None


# ═══════════════════════════════════════════════════════════════════════════════
# Security Module (src/core/security.py)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSanitizationResult:
    """Tests for the SanitizationResult dataclass."""

    def test_defaults(self):
        from src.core.security import SanitizationResult

        result = SanitizationResult(is_safe=True, sanitized="hello")
        assert result.is_safe is True
        assert result.sanitized == "hello"
        assert result.threats_detected == []
        assert result.original_length == 0
        assert result.sanitized_length == 0

    def test_with_threats(self):
        from src.core.security import SanitizationResult

        result = SanitizationResult(
            is_safe=False,
            sanitized="safe",
            threats_detected=["XSS detected"],
            original_length=100,
            sanitized_length=50,
        )
        assert result.is_safe is False
        assert len(result.threats_detected) == 1
        assert result.original_length == 100


class TestSanitizeInput:
    """Tests for the sanitize_input function."""

    def test_clean_input(self):
        from src.core.security import sanitize_input

        result = sanitize_input("Hello, world!")
        assert result.is_safe is True
        assert result.threats_detected == []
        assert "Hello" in result.sanitized

    def test_xss_script_tag(self):
        from src.core.security import sanitize_input

        result = sanitize_input('<script>alert("xss")</script>')
        assert result.is_safe is False
        assert any(
            "script" in t.lower() or "dangerous" in t.lower() for t in result.threats_detected
        )

    def test_javascript_protocol(self):
        from src.core.security import sanitize_input

        result = sanitize_input("javascript:alert(1)")
        assert result.is_safe is False

    def test_event_handler(self):
        from src.core.security import sanitize_input

        result = sanitize_input('<img onerror="alert(1)">')
        assert result.is_safe is False

    def test_eval_detection(self):
        from src.core.security import sanitize_input

        result = sanitize_input("eval(user_input)")
        assert result.is_safe is False

    def test_exec_detection(self):
        from src.core.security import sanitize_input

        result = sanitize_input("exec(code)")
        assert result.is_safe is False

    def test_import_detection(self):
        from src.core.security import sanitize_input

        result = sanitize_input("__import__('os')")
        assert result.is_safe is False

    def test_subprocess_detection(self):
        from src.core.security import sanitize_input

        result = sanitize_input("subprocess.run(cmd)")
        assert result.is_safe is False

    def test_os_system_detection(self):
        from src.core.security import sanitize_input

        result = sanitize_input("os.system('rm -rf /')")
        assert result.is_safe is False

    def test_path_traversal_detection(self):
        from src.core.security import sanitize_input

        result = sanitize_input("../../etc/passwd")
        assert result.is_safe is False

    def test_null_byte_removal(self):
        from src.core.security import sanitize_input

        result = sanitize_input("hello\x00world")
        assert "\x00" not in result.sanitized
        assert any("Null" in t for t in result.threats_detected)

    def test_length_truncation(self):
        from src.core.security import sanitize_input

        long_text = "a" * 10000
        result = sanitize_input(long_text, max_length=100)
        assert result.sanitized_length <= 100
        assert any("truncated" in t.lower() for t in result.threats_detected)

    def test_angle_bracket_encoding(self):
        from src.core.security import sanitize_input

        result = sanitize_input("<div>content</div>")
        assert "&lt;" in result.sanitized
        assert "&gt;" in result.sanitized

    def test_original_length_preserved(self):
        from src.core.security import sanitize_input

        text = "a" * 500
        result = sanitize_input(text, max_length=100)
        assert result.original_length == 500


class TestValidatePath:
    """Tests for the validate_path function."""

    def test_normal_path(self):
        from src.core.security import validate_path

        assert validate_path("/tmp/safe_file.txt") is True

    def test_path_traversal(self):
        from src.core.security import validate_path

        assert validate_path("../../etc/passwd") is False

    def test_allowed_directory_check(self):
        from src.core.security import validate_path

        assert validate_path("/tmp/safe.txt", allowed_dirs=["/tmp"]) is True

    def test_disallowed_directory(self):
        from src.core.security import validate_path

        assert validate_path("/etc/passwd", allowed_dirs=["/tmp"]) is False


class TestRateLimitConfig:
    """Tests for the RateLimitConfig dataclass."""

    def test_defaults(self):
        from src.core.security import RateLimitConfig

        rl = RateLimitConfig()
        assert rl.max_requests == 100
        assert rl.window_seconds == 60
        assert rl.burst_size == 10

    def test_requests_per_second(self):
        from src.core.security import RateLimitConfig

        rl = RateLimitConfig(max_requests=100, window_seconds=60)
        assert abs(rl.requests_per_second - 100 / 60) < 0.01

    def test_custom_values(self):
        from src.core.security import RateLimitConfig

        rl = RateLimitConfig(max_requests=200, window_seconds=120, burst_size=20)
        assert rl.max_requests == 200
        assert rl.window_seconds == 120
        assert rl.burst_size == 20


class TestSecureDefaults:
    """Tests for the SecureDefaults class."""

    def test_cors_restrictive(self):
        from src.core.security import SecureDefaults

        assert "https://trancendos.ai" in SecureDefaults.CORS_ALLOW_ORIGINS

    def test_cors_methods(self):
        from src.core.security import SecureDefaults

        assert "GET" in SecureDefaults.CORS_ALLOW_METHODS
        assert "POST" in SecureDefaults.CORS_ALLOW_METHODS

    def test_tls_min_version(self):
        from src.core.security import SecureDefaults

        assert "TLSv1.3" in SecureDefaults.TLS_MIN_VERSION

    def test_jwt_algorithm(self):
        from src.core.security import SecureDefaults

        assert SecureDefaults.JWT_ALGORITHM == "RS256"

    def test_session_cookie_secure(self):
        from src.core.security import SecureDefaults

        assert SecureDefaults.SESSION_COOKIE_SECURE is True
        assert SecureDefaults.SESSION_COOKIE_HTTPONLY is True
        assert SecureDefaults.SESSION_COOKIE_SAMESITE == "Strict"

    def test_get_cors_config(self):
        from src.core.security import SecureDefaults

        config = SecureDefaults.get_cors_config()
        assert "allow_origins" in config
        assert "allow_methods" in config
        assert "allow_headers" in config
        assert "max_age" in config
        assert config["max_age"] == 600


class TestSecurityHeaders:
    """Tests for the SECURITY_HEADERS constant."""

    def test_x_content_type_options(self):
        from src.core.security import SECURITY_HEADERS

        assert SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options(self):
        from src.core.security import SECURITY_HEADERS

        assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"

    def test_hsts(self):
        from src.core.security import SECURITY_HEADERS

        assert "Strict-Transport-Security" in SECURITY_HEADERS

    def test_csp(self):
        from src.core.security import SECURITY_HEADERS

        assert "Content-Security-Policy" in SECURITY_HEADERS

    def test_cache_control(self):
        from src.core.security import SECURITY_HEADERS

        assert "no-store" in SECURITY_HEADERS["Cache-Control"]


class TestVerifyModelIntegrity:
    """Tests for the verify_model_integrity function."""

    def test_nonexistent_file(self):
        from src.core.security import verify_model_integrity

        assert verify_model_integrity("/nonexistent/path/model.pt") is False

    def test_existing_file_no_hash(self):
        import tempfile

        from src.core.security import verify_model_integrity

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test model data")
            path = f.name
        try:
            # Without expected hash, should return True (just computes hash)
            assert verify_model_integrity(path) is True
        finally:
            os.unlink(path)

    def test_existing_file_wrong_hash(self):
        import tempfile

        from src.core.security import verify_model_integrity

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test model data")
            path = f.name
        try:
            assert verify_model_integrity(path, expected_sha256="0" * 64) is False
        finally:
            os.unlink(path)

    def test_existing_file_correct_hash(self):
        import hashlib
        import tempfile

        from src.core.security import verify_model_integrity

        content = b"test model data for hash"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            path = f.name
        expected = hashlib.sha256(content).hexdigest()
        try:
            assert verify_model_integrity(path, expected_sha256=expected) is True
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════════════
# Startup Validator (src/core/startup_validator.py)
# ═══════════════════════════════════════════════════════════════════════════════


class TestStartupValidator:
    """Tests for the startup_validator module.

    Note: The module reads ENVIRONMENT at import time into module-level
    _ENV and _IS_PROD variables. We must patch those alongside os.environ
    for production-mode tests to work correctly.
    """

    def _clean_env(self, *keys):
        """Remove specific keys from env if present."""
        env = dict(os.environ)
        for key in keys:
            env.pop(key, None)
        return env

    def test_validate_startup_dev_ok(self):
        """In development mode, missing optional vars should only warn."""
        import src.core.startup_validator as sv_mod
        from src.core.startup_validator import validate_startup

        env = self._clean_env(
            "SECRET_KEY",
            "JWT_SECRET",
            "DATABASE_URL",
            "REDIS_URL",
            "CORS_ORIGINS",
            "TRANC3_API_KEY",
            "REQUIRE_AUTH",
        )
        env["ENVIRONMENT"] = "development"
        with patch.object(sv_mod, "_IS_PROD", False), patch.dict(os.environ, env, clear=True):
            validate_startup()  # Should not raise

    def test_validate_startup_prod_missing_secret_key(self):
        """In production, missing SECRET_KEY should raise RuntimeError."""
        import src.core.startup_validator as sv_mod
        from src.core.startup_validator import validate_startup

        env = self._clean_env("SECRET_KEY", "JWT_SECRET", "DATABASE_URL", "REDIS_URL")
        env["ENVIRONMENT"] = "production"
        env["CORS_ORIGINS"] = "https://example.com"
        with patch.object(sv_mod, "_IS_PROD", True), patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="SECRET_KEY"):
                validate_startup()

    def test_validate_startup_prod_missing_jwt_secret(self):
        """In production, missing JWT_SECRET should raise RuntimeError."""
        import src.core.startup_validator as sv_mod
        from src.core.startup_validator import validate_startup

        env = self._clean_env("JWT_SECRET")
        env["ENVIRONMENT"] = "production"
        env["SECRET_KEY"] = "a" * 32
        env["CORS_ORIGINS"] = "https://example.com"
        env["DATABASE_URL"] = "sqlite:///test.db"
        env["REDIS_URL"] = "redis://localhost:6379"
        with patch.object(sv_mod, "_IS_PROD", True), patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="JWT_SECRET"):
                validate_startup()

    def test_validate_startup_prod_wildcard_cors(self):
        """In production, CORS_ORIGINS=* should raise RuntimeError."""
        import src.core.startup_validator as sv_mod
        from src.core.startup_validator import validate_startup

        env = {}
        env["ENVIRONMENT"] = "production"
        env["SECRET_KEY"] = "a" * 32
        env["JWT_SECRET"] = "b" * 32
        env["DATABASE_URL"] = "sqlite:///test.db"
        env["REDIS_URL"] = "redis://localhost:6379"
        env["CORS_ORIGINS"] = "*"
        with patch.object(sv_mod, "_IS_PROD", True), patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
                validate_startup()

    def test_validate_startup_prod_missing_database_url(self):
        """In production, missing DATABASE_URL should raise RuntimeError."""
        import src.core.startup_validator as sv_mod
        from src.core.startup_validator import validate_startup

        env = self._clean_env("DATABASE_URL")
        env["ENVIRONMENT"] = "production"
        env["SECRET_KEY"] = "a" * 32
        env["JWT_SECRET"] = "b" * 32
        env["CORS_ORIGINS"] = "https://example.com"
        env["REDIS_URL"] = "redis://localhost:6379"
        with patch.object(sv_mod, "_IS_PROD", True), patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="DATABASE_URL"):
                validate_startup()

    def test_validate_startup_prod_missing_redis_url(self):
        """In production, missing REDIS_URL should raise RuntimeError."""
        import src.core.startup_validator as sv_mod
        from src.core.startup_validator import validate_startup

        env = self._clean_env("REDIS_URL")
        env["ENVIRONMENT"] = "production"
        env["SECRET_KEY"] = "a" * 32
        env["JWT_SECRET"] = "b" * 32
        env["CORS_ORIGINS"] = "https://example.com"
        env["DATABASE_URL"] = "sqlite:///test.db"
        with patch.object(sv_mod, "_IS_PROD", True), patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="REDIS_URL"):
                validate_startup()

    def test_validate_startup_prod_short_secret_key(self):
        """In production, a short SECRET_KEY should raise RuntimeError."""
        import src.core.startup_validator as sv_mod
        from src.core.startup_validator import validate_startup

        env = {}
        env["ENVIRONMENT"] = "production"
        env["SECRET_KEY"] = "tooshort"
        env["JWT_SECRET"] = "b" * 32
        env["CORS_ORIGINS"] = "https://example.com"
        env["DATABASE_URL"] = "sqlite:///test.db"
        env["REDIS_URL"] = "redis://localhost:6379"
        with patch.object(sv_mod, "_IS_PROD", True), patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="too short"):
                validate_startup()

    def test_validate_startup_prod_short_jwt_secret(self):
        """In production, a short JWT_SECRET should raise RuntimeError."""
        import src.core.startup_validator as sv_mod
        from src.core.startup_validator import validate_startup

        env = {}
        env["ENVIRONMENT"] = "production"
        env["SECRET_KEY"] = "a" * 32
        env["JWT_SECRET"] = "tooshort"
        env["CORS_ORIGINS"] = "https://example.com"
        env["DATABASE_URL"] = "sqlite:///test.db"
        env["REDIS_URL"] = "redis://localhost:6379"
        with patch.object(sv_mod, "_IS_PROD", True), patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="too short"):
                validate_startup()

    def test_validate_startup_prod_require_auth_no_api_key(self):
        """In production with REQUIRE_AUTH=true but no TRANC3_API_KEY, should raise."""
        import src.core.startup_validator as sv_mod
        from src.core.startup_validator import validate_startup

        env = self._clean_env("TRANC3_API_KEY")
        env["ENVIRONMENT"] = "production"
        env["SECRET_KEY"] = "a" * 32
        env["JWT_SECRET"] = "b" * 32
        env["CORS_ORIGINS"] = "https://example.com"
        env["DATABASE_URL"] = "sqlite:///test.db"
        env["REDIS_URL"] = "redis://localhost:6379"
        env["REQUIRE_AUTH"] = "true"
        with patch.object(sv_mod, "_IS_PROD", True), patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="TRANC3_API_KEY"):
                validate_startup()

    def test_validate_startup_prod_success(self):
        """In production with all required vars, should pass without raising."""
        import src.core.startup_validator as sv_mod
        from src.core.startup_validator import validate_startup

        env = {}
        env["ENVIRONMENT"] = "production"
        env["SECRET_KEY"] = "a" * 32
        env["JWT_SECRET"] = "b" * 32
        env["CORS_ORIGINS"] = "https://example.com"
        env["DATABASE_URL"] = "sqlite:///test.db"
        env["REDIS_URL"] = "redis://localhost:6379"
        with patch.object(sv_mod, "_IS_PROD", True), patch.dict(os.environ, env, clear=True):
            validate_startup()  # Should not raise

    def test_validate_startup_dev_generates_secret_key(self):
        """In development, missing SECRET_KEY should be auto-generated."""
        import src.core.startup_validator as sv_mod
        from src.core.startup_validator import validate_startup

        env = self._clean_env("SECRET_KEY", "JWT_SECRET")
        env["ENVIRONMENT"] = "development"
        with patch.object(sv_mod, "_IS_PROD", False), patch.dict(os.environ, env, clear=True):
            validate_startup()
            assert len(os.environ.get("SECRET_KEY", "")) >= 32

    def test_validate_startup_dev_generates_jwt_secret(self):
        """In development, missing JWT_SECRET should be auto-generated."""
        import src.core.startup_validator as sv_mod
        from src.core.startup_validator import validate_startup

        env = self._clean_env("JWT_SECRET")
        env["ENVIRONMENT"] = "development"
        with patch.object(sv_mod, "_IS_PROD", False), patch.dict(os.environ, env, clear=True):
            validate_startup()
            assert len(os.environ.get("JWT_SECRET", "")) >= 32
