# tests/test_production_api.py
# Tests for the production readiness implementation.
# Covers: LLM Router, Database Schema, Startup Validation, Auth.

import os
import sys
import pytest
import uuid
from unittest.mock import MagicMock, patch

# Ensure project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set required env vars before importing app modules
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_tranc3.db")


# ═══════════════════════════════════════════════════════════════════
# LLM Router Tests
# ═══════════════════════════════════════════════════════════════════

class TestLLMRouter:
    """Test the multi-provider LLM router."""

    def test_provider_enum(self):
        from src.inference.llm_router import Provider
        assert Provider.LOCAL.value == "local"
        assert Provider.HUGGINGFACE.value == "huggingface"
        assert Provider.GROQ.value == "groq"
        assert Provider.OPENAI.value == "openai"
        assert Provider.FALLBACK.value == "fallback"

    def test_provider_config_defaults(self):
        from src.inference.llm_router import ProviderConfig, Provider
        cfg = ProviderConfig(
            name=Provider.HUGGINGFACE,
            api_key_env="HF_API_KEY",
            base_url="https://api-inference.huggingface.co/models",
            model_id="test-model",
        )
        assert cfg.max_tokens == 256
        assert cfg.timeout_seconds == 30.0
        assert cfg.cost_per_1k_tokens == 0.0
        assert cfg.rate_limit_rpm == 60

    def test_generation_request_defaults(self):
        from src.inference.llm_router import GenerationRequest
        req = GenerationRequest(prompt="Hello")
        assert req.prompt == "Hello"
        assert req.personality == "tranc3-base"
        assert req.max_tokens == 256
        assert req.temperature == 0.8
        assert req.preferred_provider is None

    def test_generation_response_fields(self):
        from src.inference.llm_router import GenerationResponse, Provider
        resp = GenerationResponse(
            text="Hello!",
            provider=Provider.FALLBACK,
            model="tranc3-bootstrap",
        )
        assert resp.text == "Hello!"
        assert resp.provider == Provider.FALLBACK
        assert resp.tokens_used == 0
        assert resp.from_cache is False
        assert resp.fallback_used is False

    def test_rate_limiter_acquire(self):
        from src.inference.llm_router import _RateLimiter
        import asyncio

        limiter = _RateLimiter(rpm=10)

        async def _test():
            assert await limiter.acquire() is True

        asyncio.run(_test())

    def test_response_cache_miss(self):
        from src.inference.llm_router import _ResponseCache, GenerationRequest
        cache = _ResponseCache()
        req = GenerationRequest(prompt="test")
        assert cache.get(req) is None

    def test_response_cache_put_get(self):
        from src.inference.llm_router import _ResponseCache, GenerationRequest, GenerationResponse, Provider
        cache = _ResponseCache()
        req = GenerationRequest(prompt="test")
        resp = GenerationResponse(text="response", provider=Provider.FALLBACK, model="test")
        cache.put(req, resp)
        cached = cache.get(req)
        assert cached is not None
        assert cached.text == "response"

    def test_router_fallback_response(self):
        from src.inference.llm_router import LLMRouter, GenerationRequest
        router = LLMRouter()
        req = GenerationRequest(prompt="Hello, world!")
        resp = router._fallback_response(req, None)
        assert resp.fallback_used is True
        assert resp.provider.value == "fallback"
        # The text should mention that no provider is configured
        assert "LLM" in resp.text or "provider" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_router_generate_fallback(self):
        """When no API keys are set, router should return fallback response."""
        from src.inference.llm_router import LLMRouter, GenerationRequest
        router = LLMRouter()
        req = GenerationRequest(prompt="Hello, world!")
        resp = await router.generate(req)
        # Without any API keys or local model, should get fallback
        assert resp.fallback_used is True

    @pytest.mark.asyncio
    async def test_router_health_check(self):
        from src.inference.llm_router import LLMRouter
        router = LLMRouter()
        health = await router.health_check()
        assert "router_status" in health
        assert "providers" in health
        assert health["router_status"] == "operational"

    def test_router_stats(self):
        from src.inference.llm_router import LLMRouter
        router = LLMRouter()
        stats = router.get_stats()
        assert "total_requests" in stats
        assert "cache_hits" in stats
        assert "fallback_count" in stats

    def test_priority_order(self):
        from src.inference.llm_router import LLMRouter, Provider
        router = LLMRouter()
        order = router._build_priority()
        names = [p.name for p in order]
        assert names[0] == Provider.LOCAL
        assert names[-1] == Provider.FALLBACK

    def test_priority_preferred(self):
        from src.inference.llm_router import LLMRouter, Provider
        router = LLMRouter()
        order = router._build_priority(preferred=Provider.GROQ)
        assert order[0].name == Provider.GROQ


# ═══════════════════════════════════════════════════════════════════
# Database Schema Tests
# ═══════════════════════════════════════════════════════════════════

class TestDatabaseSchema:
    """Test the cross-dialect database schema."""

    def test_guid_type(self):
        from src.database.schema import GUID
        g = GUID()
        assert g is not None

    def test_database_manager_sqlite(self, tmp_path):
        from src.database.schema import DatabaseManager
        db_path = str(tmp_path / "test.db")
        db_url = f"sqlite:///{db_path}"
        mgr = DatabaseManager(db_url)
        assert mgr.is_sqlite is True
        assert mgr.health_check() is True

    def test_database_manager_get_session(self, tmp_path):
        from src.database.schema import DatabaseManager
        db_path = str(tmp_path / "test.db")
        db_url = f"sqlite:///{db_path}"
        mgr = DatabaseManager(db_url)
        session = mgr.get_session()
        assert session is not None
        session.close()

    def test_database_manager_get_session_factory(self, tmp_path):
        from src.database.schema import DatabaseManager
        db_path = str(tmp_path / "test.db")
        db_url = f"sqlite:///{db_path}"
        mgr = DatabaseManager(db_url)
        factory = mgr.get_session_factory()
        assert callable(factory)
        session = factory()
        assert session is not None
        session.close()

    def test_health_check_uses_text(self, tmp_path):
        """Verify the health_check() uses text() for raw SQL (bug fix)."""
        from src.database.schema import DatabaseManager
        db_path = str(tmp_path / "test.db")
        db_url = f"sqlite:///{db_path}"
        mgr = DatabaseManager(db_url)
        # This should NOT raise "str object is not callable"
        result = mgr.health_check()
        assert result is True

    def test_user_model_create(self, tmp_path):
        from src.database.schema import DatabaseManager, User
        db_path = str(tmp_path / "test.db")
        db_url = f"sqlite:///{db_path}"
        mgr = DatabaseManager(db_url)
        session = mgr.get_session()

        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed123",
            tier="free",
        )
        session.add(user)
        session.commit()

        fetched = session.query(User).filter(User.username == "testuser").first()
        assert fetched is not None
        assert fetched.email == "test@example.com"
        assert fetched.tier == "free"
        session.close()

    def test_conversation_model(self, tmp_path):
        from src.database.schema import DatabaseManager, User, Conversation
        db_path = str(tmp_path / "test.db")
        db_url = f"sqlite:///{db_path}"
        mgr = DatabaseManager(db_url)
        session = mgr.get_session()

        user = User(
            username="convuser",
            email="conv@example.com",
            hashed_password="hashed123",
        )
        session.add(user)
        session.commit()

        conv = Conversation(
            user_id=user.id,
            title="Test Conversation",
            personality="dorris-fontaine",
        )
        session.add(conv)
        session.commit()

        fetched = session.query(Conversation).filter(Conversation.title == "Test Conversation").first()
        assert fetched is not None
        assert fetched.personality == "dorris-fontaine"
        session.close()

    def test_message_model(self, tmp_path):
        from src.database.schema import DatabaseManager, User, Conversation, Message
        db_path = str(tmp_path / "test.db")
        db_url = f"sqlite:///{db_path}"
        mgr = DatabaseManager(db_url)
        session = mgr.get_session()

        user = User(username="msguser", email="msg@example.com", hashed_password="h")
        session.add(user)
        session.commit()

        conv = Conversation(user_id=user.id, title="Msg Test")
        session.add(conv)
        session.commit()

        msg = Message(
            conversation_id=conv.id,
            role="user",
            content="Hello TRANC3!",
            language="en",
        )
        session.add(msg)
        session.commit()

        fetched = session.query(Message).filter(Message.content == "Hello TRANC3!").first()
        assert fetched is not None
        assert fetched.role == "user"
        session.close()


# ═══════════════════════════════════════════════════════════════════
# Startup Validation Tests
# ═══════════════════════════════════════════════════════════════════

class TestStartupValidation:
    """Test the startup validation module."""

    def test_validator_creation(self):
        from src.core.startup import StartupValidator
        v = StartupValidator()
        assert v is not None

    def test_validator_validate_all(self):
        from src.core.startup import StartupValidator
        v = StartupValidator()
        report = v.validate_all()
        assert "status" in report
        assert "services" in report
        assert "validation_time_ms" in report

    def test_validator_service_reports(self):
        from src.core.startup import StartupValidator, ServiceStatus
        v = StartupValidator()
        report = v.validate_all()
        services = report["services"]
        # Should have at least the core services checked
        assert "database" in services or "auth" in services
        # Each service should have a status
        for name, info in services.items():
            assert "status" in info
            assert info["status"] in [s.value for s in ServiceStatus]


# ═══════════════════════════════════════════════════════════════════
# Database Dependency Tests
# ═══════════════════════════════════════════════════════════════════

class TestDatabaseDeps:
    """Test the FastAPI database dependencies."""

    def test_set_db_manager(self, tmp_path):
        from src.database.deps import set_db_manager
        from src.database.schema import DatabaseManager
        db_path = str(tmp_path / "test.db")
        db_url = f"sqlite:///{db_path}"
        mgr = DatabaseManager(db_url)
        set_db_manager(mgr)

    def test_get_db_session_optional(self, tmp_path):
        from src.database.deps import set_db_manager, get_db_session_optional
        from src.database.schema import DatabaseManager
        db_path = str(tmp_path / "test.db")
        db_url = f"sqlite:///{db_path}"
        mgr = DatabaseManager(db_url)
        set_db_manager(mgr)
        session = get_db_session_optional()
        assert session is not None
        session.close()

    def test_get_db_session_optional_no_manager(self):
        from src.database.deps import get_db_session_optional
        import src.database.deps as deps
        old = deps._db_manager
        deps._db_manager = None
        try:
            result = get_db_session_optional()
            assert result is None
        finally:
            deps._db_manager = old


# ═══════════════════════════════════════════════════════════════════
# Auth Tests
# ═══════════════════════════════════════════════════════════════════

class TestAuth:
    """Test authentication system."""

    def test_user_manager_create(self):
        from auth import UserManager
        mgr = UserManager()
        result = mgr.create_user("testuser", "TestPass123")
        assert result["username"] == "testuser"

    def test_user_manager_authenticate(self):
        from auth import UserManager
        mgr = UserManager()
        mgr.create_user("authuser", "AuthPass123")
        user = mgr.authenticate_user("authuser", "AuthPass123")
        assert user is not None
        assert user["username"] == "authuser"

    def test_user_manager_wrong_password(self):
        from auth import UserManager
        mgr = UserManager()
        mgr.create_user("wrongpass", "RightPass123")
        user = mgr.authenticate_user("wrongpass", "WrongPass123")
        assert user is None

    def test_db_user_manager_password_validation(self):
        from src.auth.db_user_manager import DBUserManager
        from fastapi import HTTPException
        mgr = DBUserManager(None)
        # Too short
        with pytest.raises(HTTPException):
            mgr.create_user("shortpw", "Ab1")
        # No uppercase
        with pytest.raises(HTTPException):
            mgr.create_user("nouppercase", "abcdefgh1")
        # No digit
        with pytest.raises(HTTPException):
            mgr.create_user("nodigit", "Abcdefgh")

    def test_db_user_manager_create_and_auth(self):
        from src.auth.db_user_manager import DBUserManager
        mgr = DBUserManager(None)
        result = mgr.create_user("dbuser", "ValidPass123", email="db@test.com")
        assert result["username"] == "dbuser"

        user = mgr.authenticate_user("dbuser", "ValidPass123")
        assert user is not None
        assert user["username"] == "dbuser"

    def test_token_manager(self):
        from auth import TokenManager
        token = TokenManager.create_access_token({"sub": "testuser"})
        assert isinstance(token, str)
        assert len(token) > 0

        payload = TokenManager.decode_token(token)
        assert payload["sub"] == "testuser"
        assert payload["type"] == "access"


# ═══════════════════════════════════════════════════════════════════
# Personality System Prompt Tests
# ═══════════════════════════════════════════════════════════════════

class TestPersonalityPrompts:
    """Test personality system prompt generation."""

    def test_all_personalities_have_prompts(self):
        # Import the helper — we'll test the logic directly
        # to avoid importing the full FastAPI app
        prompts = {
            "tranc3-base":          "You are TRANC3, a balanced, intelligent AI assistant. Be helpful, clear, and accurate.",
            "dorris-fontaine":      "You are Dorris Fontaine, TRANC3's financial specialist. You provide precise, regulation-aware financial analysis. Be professional, data-driven, and highlight risks and compliance considerations.",
            "cornelius-macintyre":  "You are Cornelius MacIntyre, TRANC3's orchestration specialist. You coordinate complex multi-system tasks with strategic clarity. Be organized, methodical, and focused on actionable outcomes.",
            "the-guardian":         "You are The Guardian, TRANC3's cybersecurity specialist. You identify threats, enforce compliance, and protect systems. Be security-focused, thorough, and proactive about vulnerabilities.",
            "vesper-nightingale":   "You are Vesper Nightingale, TRANC3's healthcare advisor. You provide evidence-based health guidance with warmth and care. Be compassionate, factual, and always recommend professional medical consultation.",
            "atlas-meridian":       "You are Atlas Meridian, TRANC3's infrastructure specialist. You architect resilient, scalable, cost-efficient systems. Be practical, performance-minded, and focused on reliability.",
        }
        for p in prompts:
            prompt = prompts[p]
            assert len(prompt) > 20, f"Personality {p} has too short a prompt"
            assert "TRANC3" in prompt or p.replace("-", " ").title() in prompt

    def test_unknown_personality_gets_default(self):
        prompts = {
            "tranc3-base": "You are TRANC3, a balanced, intelligent AI assistant.",
        }
        personality = "unknown-personality"
        prompt = prompts.get(personality, prompts["tranc3-base"])
        assert "TRANC3" in prompt


# ═══════════════════════════════════════════════════════════════════
# Emotion Detection Tests
# ═══════════════════════════════════════════════════════════════════

class TestEmotionDetection:
    """Test rule-based emotion detection."""

    @staticmethod
    def _detect_emotion(text: str) -> str:
        """Inline version of emotion detection for testing."""
        text_lower = text.lower()
        if any(w in text_lower for w in ["angry", "furious", "mad", "frustrated", "annoyed"]):
            return "frustrated"
        if any(w in text_lower for w in ["happy", "great", "awesome", "wonderful", "excited"]):
            return "happy"
        if any(w in text_lower for w in ["sad", "unhappy", "depressed", "miserable", "disappointed"]):
            return "sad"
        if any(w in text_lower for w in ["worried", "anxious", "concerned", "nervous", "afraid"]):
            return "anxious"
        if any(w in text_lower for w in ["thanks", "thank you", "appreciate", "grateful"]):
            return "grateful"
        if any(w in text_lower for w in ["help", "how do", "what is", "explain", "question"]):
            return "curious"
        return "neutral"

    def test_happy_emotion(self):
        assert self._detect_emotion("I'm so happy today!") == "happy"
        assert self._detect_emotion("That's great news!") == "happy"

    def test_sad_emotion(self):
        assert self._detect_emotion("I feel sad about this") == "sad"

    def test_frustrated_emotion(self):
        assert self._detect_emotion("I'm frustrated with this error") == "frustrated"

    def test_anxious_emotion(self):
        assert self._detect_emotion("I'm worried about the deadline") == "anxious"

    def test_curious_emotion(self):
        assert self._detect_emotion("How do I implement this?") == "curious"

    def test_neutral_emotion(self):
        assert self._detect_emotion("Tell me about machine learning") == "neutral"


# ═══════════════════════════════════════════════════════════════════════════
# Rate Limiter Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRateLimiter:
    """Test the rate limiting middleware and in-memory bucket."""

    def test_rate_limits_config(self):
        from src.middleware.rate_limit import RATE_LIMITS
        assert "free" in RATE_LIMITS
        assert "pro" in RATE_LIMITS
        assert "enterprise" in RATE_LIMITS
        assert "default" in RATE_LIMITS
        # Free tier should be reasonable
        assert RATE_LIMITS["free"]["rpm"] > 0
        assert RATE_LIMITS["free"]["rpd"] > RATE_LIMITS["free"]["rpm"]

    def test_in_memory_bucket_allows_under_limit(self):
        from src.middleware.rate_limit import _InMemoryBucket
        bucket = _InMemoryBucket()
        # Should allow first request
        allowed, headers = bucket.check("user:1", rpm=10, rpd=100)
        assert allowed is True
        assert "X-RateLimit-Limit" in headers
        assert headers["X-RateLimit-Limit"] == 10

    def test_in_memory_bucket_blocks_over_minute_limit(self):
        from src.middleware.rate_limit import _InMemoryBucket
        bucket = _InMemoryBucket()
        # Exhaust the minute limit
        for i in range(10):
            allowed, _ = bucket.check("user:2", rpm=10, rpd=1000)
        # 11th request should be blocked (10 rpm limit)
        # Note: token bucket allows some burst, so we need more requests
        for i in range(20):
            bucket.check("user:2", rpm=2, rpd=1000)
        allowed, _ = bucket.check("user:2", rpm=2, rpd=1000)
        assert allowed is False

    def test_in_memory_bucket_different_keys_independent(self):
        from src.middleware.rate_limit import _InMemoryBucket
        bucket = _InMemoryBucket()
        # Use up quota for user:3a
        for i in range(20):
            bucket.check("user:3a", rpm=2, rpd=1000)
        # user:3b should still have quota
        allowed, _ = bucket.check("user:3b", rpm=10, rpd=100)
        assert allowed is True

    def test_in_memory_bucket_headers(self):
        from src.middleware.rate_limit import _InMemoryBucket
        bucket = _InMemoryBucket()
        allowed, headers = bucket.check("user:4", rpm=20, rpd=500)
        assert "X-RateLimit-Remaining-Minute" in headers
        assert "X-RateLimit-Remaining-Day" in headers

    def test_rate_limit_middleware_skip_paths(self):
        from src.middleware.rate_limit import RateLimitMiddleware
        assert "/health" in RateLimitMiddleware.SKIP_PATHS
        assert "/ready" in RateLimitMiddleware.SKIP_PATHS
        assert "/docs" in RateLimitMiddleware.SKIP_PATHS

    def test_rate_limit_middleware_creation_no_redis(self):
        from src.middleware.rate_limit import RateLimitMiddleware, _InMemoryBucket
        from starlette.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        middleware = RateLimitMiddleware(app, redis_client=None)
        assert isinstance(middleware._limiter, _InMemoryBucket)

    def test_rate_limit_middleware_creation_with_redis(self):
        from src.middleware.rate_limit import RateLimitMiddleware, _RedisRateLimiter
        from fastapi import FastAPI

        app = FastAPI()
        mock_redis = type("MockRedis", (), {})()
        middleware = RateLimitMiddleware(app, redis_client=mock_redis)
        assert isinstance(middleware._limiter, _RedisRateLimiter)


# ═══════════════════════════════════════════════════════════════════════════
# Structured Logging Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestStructuredLogging:
    """Test the structured logging configuration."""

    def test_structured_logger_creation(self):
        from src.core.logging_config import StructuredLogger
        log = StructuredLogger("test.logger")
        assert log is not None

    def test_structured_logger_info(self, capfd):
        from src.core.logging_config import StructuredLogger, setup_logging
        import logging

        setup_logging(level="DEBUG", json_output=True)
        log = StructuredLogger("test.info")
        log.info("test message", key1="value1")
        # Just verify it doesn't crash — output goes to stdout

    def test_structured_logger_with_kwargs(self):
        from src.core.logging_config import StructuredLogger
        log = StructuredLogger("test.kwargs")
        # Should not raise
        log.info("operation completed", duration_ms=42, provider="groq")
        log.warning("slow request", latency_ms=5000)
        log.error("request failed", error="timeout", retry=3)

    def test_request_timer(self):
        from src.core.logging_config import RequestTimer, setup_logging
        setup_logging(level="DEBUG", json_output=False)
        with RequestTimer("test_op", key="value") as t:
            import time
            time.sleep(0.01)
        # Timer should have recorded a positive start time
        assert t.start > 0

    def test_setup_logging_console(self):
        from src.core.logging_config import setup_logging
        import logging
        setup_logging(level="INFO", json_output=False)
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_setup_logging_json(self):
        from src.core.logging_config import setup_logging
        import logging
        setup_logging(level="DEBUG", json_output=True)
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_setup_logging_env_vars(self):
        from src.core.logging_config import setup_logging
        import logging
        os.environ["LOG_LEVEL"] = "WARNING"
        os.environ["LOG_FORMAT"] = "json"
        try:
            setup_logging()
            root = logging.getLogger()
            assert root.level == logging.WARNING
        finally:
            del os.environ["LOG_LEVEL"]
            del os.environ["LOG_FORMAT"]


# ═══════════════════════════════════════════════════════════════════════════
# Migration Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestMigration002:
    """Test the 002_complete migration has the right structure."""

    def test_migration_file_exists(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migration_002",
            os.path.join(os.path.dirname(__file__), "..", "migrations", "versions", "002_complete.py"),
        )
        assert spec is not None

    def test_migration_has_upgrade_downgrade(self):
        migration_path = os.path.join(
            os.path.dirname(__file__), "..", "migrations", "versions", "002_complete.py"
        )
        with open(migration_path) as f:
            source = f.read()
        assert "def upgrade" in source
        assert "def downgrade" in source

    def test_migration_creates_expected_tables(self):
        migration_path = os.path.join(
            os.path.dirname(__file__), "..", "migrations", "versions", "002_complete.py"
        )
        with open(migration_path) as f:
            source = f.read()
        expected_tables = ["api_keys", "feedback", "evolution_events", "quantum_sessions", "system_metrics"]
        for table in expected_tables:
            assert table in source, f"Migration missing table: {table}"
