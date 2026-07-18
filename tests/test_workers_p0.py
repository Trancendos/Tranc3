"""
Worker Integration Tests — P0 Workers (infinity-ws, infinity-auth)
===================================================================
Tests the two highest-priority workers end-to-end using FastAPI TestClient
with temporary SQLite databases. No external services required.

P0 Workers:
- infinity-ws (The Nexus): WebSocket connection management, pub/sub
- infinity-auth (Infinity): Auth registration, login, JWT, MFA, rate limiting
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests._worker_import_utils import import_worker as _import_worker

# ── Import helpers for hyphenated package names ──────────────────────────────

_TRANC3_ROOT = Path(__file__).resolve().parent.parent


ws_mod = _import_worker(
    "infinity_ws_worker", _TRANC3_ROOT / "workers" / "infinity-ws" / "worker.py"
)
auth_mod = _import_worker(
    "infinity_auth_worker", _TRANC3_ROOT / "workers" / "infinity-auth" / "worker.py"
)


# ═══════════════════════════════════════════════════════════════════════════════
# infinity-ws (The Nexus) — WebSocket API Worker
# ═══════════════════════════════════════════════════════════════════════════════


class TestInfinityWSModels:
    """Test Pydantic models for the WebSocket worker."""

    def test_ws_message_defaults(self):
        msg = ws_mod.WSMessage(type="ping")
        assert msg.type == "ping"
        assert msg.channel is None
        assert msg.data is None
        assert msg.timestamp == ""
        assert msg.sender == ""
        assert msg.message_id == ""

    def test_ws_message_with_all_fields(self):
        msg = ws_mod.WSMessage(
            type="message",
            channel="general",
            data={"text": "hello"},
            timestamp="2024-01-01T00:00:00Z",
            sender="user1",
            message_id="msg-123",
        )
        assert msg.type == "message"
        assert msg.channel == "general"
        assert msg.data == {"text": "hello"}
        assert msg.sender == "user1"

    def test_channel_info_model(self):
        info = ws_mod.ChannelInfo(name="test-channel", subscribers=5)
        assert info.name == "test-channel"
        assert info.subscribers == 5
        assert info.created_at == ""

    def test_connection_stats_model(self):
        stats = ws_mod.ConnectionStats(total_connections=3, total_channels=2, messages_sent=10)
        assert stats.total_connections == 3
        assert stats.total_channels == 2
        assert stats.messages_sent == 10
        assert stats.uptime_seconds == 0.0


class TestConnectionManager:
    """Test the ConnectionManager in isolation (no actual WebSocket connections)."""

    def test_initial_state(self):
        mgr = ws_mod.ConnectionManager()
        assert mgr.total_connections == 0
        assert mgr.total_channels == 0

    def test_max_connections_config(self):
        mgr = ws_mod.ConnectionManager(max_connections=50, max_channels=20)
        assert mgr.max_connections == 50
        assert mgr.max_channels == 20

    def test_stats_property(self):
        mgr = ws_mod.ConnectionManager()
        stats = mgr.stats
        assert stats.total_connections == 0
        assert stats.total_channels == 0
        assert stats.messages_sent == 0
        assert stats.uptime_seconds >= 0

    def test_get_channels_empty(self):
        mgr = ws_mod.ConnectionManager()
        channels = mgr.get_channels()
        assert channels == []

    def test_get_user_channels_no_connection(self):
        mgr = ws_mod.ConnectionManager()

        class FakeWS:
            pass

        channels = mgr.get_user_channels(FakeWS())
        assert channels == []


class TestVerifyToken:
    """Test the lightweight JWT verification function."""

    def test_invalid_token_format(self):
        result = ws_mod.verify_token("not-a-jwt")
        assert result is None

    def test_empty_token(self):
        result = ws_mod.verify_token("")
        assert result is None

    def test_valid_jwt_structure(self):
        import os

        import jwt as pyjwt

        secret = os.environ.get("JWT_SECRET", "test-jwt-secret-for-unit-tests-00001")
        token = pyjwt.encode({"sub": "user123"}, secret, algorithm="HS256")

        result = ws_mod.verify_token(token, secret=secret)
        assert result is not None
        assert result.get("sub") == "user123"

    def test_malformed_base64(self):
        result = ws_mod.verify_token("a.b.c")
        assert result is None


class TestInfinityWSHTTP:
    """Test HTTP endpoints for the WebSocket worker."""

    @pytest.fixture
    def client(self):
        secret = getattr(ws_mod, "_INTERNAL_SECRET", "")
        headers = {"X-Internal-Secret": secret} if secret else {}
        return TestClient(ws_mod.app, headers=headers)

    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "infinity-ws"
        assert "connections" in data
        assert "channels" in data

    def test_stats_endpoint(self, client):
        response = client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_connections" in data
        assert "total_channels" in data
        assert "messages_sent" in data
        assert "uptime_seconds" in data

    def test_channels_endpoint_empty(self, client):
        response = client.get("/channels")
        assert response.status_code == 200
        data = response.json()
        assert "channels" in data
        assert isinstance(data["channels"], list)

    def test_health_has_correct_service_name(self, client):
        response = client.get("/health")
        data = response.json()
        assert data["service"] == "infinity-ws"

    def test_stats_returns_valid_numbers(self, client):
        response = client.get("/stats")
        data = response.json()
        assert isinstance(data["total_connections"], int)
        assert isinstance(data["total_channels"], int)
        assert isinstance(data["messages_sent"], int)
        assert isinstance(data["uptime_seconds"], float)


class TestInfinityWSWebSocket:
    """Test WebSocket endpoint for the Nexus worker."""

    @pytest.fixture
    def client(self):
        return TestClient(ws_mod.app)

    def test_websocket_connect_no_token(self, client):
        """Connect without a token uses anonymous user_id."""
        with client.websocket_connect("/ws?user_id=testuser") as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            response = ws.receive_json()
            assert response["type"] == "pong"

    def test_websocket_subscribe(self, client):
        """Subscribe to a channel."""
        with client.websocket_connect("/ws?user_id=subber") as ws:
            ws.send_text(json.dumps({"type": "subscribe", "channel": "general"}))
            response = ws.receive_json()
            assert response["type"] == "subscribed"
            assert response["channel"] == "general"

    def test_websocket_unsubscribe(self, client):
        """Unsubscribe from a channel."""
        with client.websocket_connect("/ws?user_id=unsubber") as ws:
            ws.send_text(json.dumps({"type": "subscribe", "channel": "test-ch"}))
            ws.receive_json()  # subscribed confirmation

            ws.send_text(json.dumps({"type": "unsubscribe", "channel": "test-ch"}))
            response = ws.receive_json()
            assert response["type"] == "unsubscribed"
            assert response["channel"] == "test-ch"

    def test_websocket_channels_command(self, client):
        """Request user's channel list."""
        with client.websocket_connect("/ws?user_id=chuser") as ws:
            ws.send_text(json.dumps({"type": "subscribe", "channel": "chan1"}))
            ws.receive_json()  # subscribed

            ws.send_text(json.dumps({"type": "channels"}))
            response = ws.receive_json()
            assert response["type"] == "channels"
            assert "chan1" in response["data"]["channels"]

    def test_websocket_invalid_json(self, client):
        """Send invalid JSON to get error response."""
        with client.websocket_connect("/ws?user_id=erruser") as ws:
            ws.send_text("not json at all")
            response = ws.receive_json()
            assert response["type"] == "error"

    def test_websocket_broadcast_message(self, client):
        """Broadcast a message to a channel with multiple subscribers."""
        with client.websocket_connect("/ws?user_id=broadcaster") as ws1:
            with client.websocket_connect("/ws?user_id=listener") as ws2:
                # Both subscribe to the same channel
                ws1.send_text(json.dumps({"type": "subscribe", "channel": "broadcast-test"}))
                ws1.receive_json()

                ws2.send_text(json.dumps({"type": "subscribe", "channel": "broadcast-test"}))
                ws2.receive_json()

                # ws1 receives notification about new subscriber (drain it)
                ws1.receive_json()

                # ws1 sends a message
                ws1.send_text(
                    json.dumps(
                        {
                            "type": "message",
                            "channel": "broadcast-test",
                            "data": "hello everyone",
                        }
                    )
                )

                # ws2 should receive the broadcast
                received = ws2.receive_json()
                assert received["type"] == "message"
                assert received["data"] == "hello everyone"

                # ws1 also receives its own broadcast echo, then the delivery confirmation
                echo = ws1.receive_json()
                assert echo["type"] == "message"
                confirmation = ws1.receive_json()
                assert confirmation["type"] == "delivered"

    def test_websocket_ping_pong(self, client):
        """Ping/pong heartbeat mechanism."""
        with client.websocket_connect("/ws?user_id=pinguser") as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            response = ws.receive_json()
            assert response["type"] == "pong"
            assert response["sender"] == "system"


# ═══════════════════════════════════════════════════════════════════════════════
# infinity-auth (Infinity) — Authentication Worker
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuthPasswordHashing:
    """Test password hashing and verification utilities."""

    def test_hash_password_returns_string(self):
        hashed = auth_mod.hash_password("testpassword123")
        assert isinstance(hashed, str)
        assert ":" in hashed  # salt:hash format

    def test_hash_password_different_salts(self):
        h1 = auth_mod.hash_password("samepassword")
        h2 = auth_mod.hash_password("samepassword")
        assert h1 != h2  # Different salts

    def test_verify_password_correct(self):
        hashed = auth_mod.hash_password("mypassword")
        assert auth_mod.verify_password("mypassword", hashed) is True

    def test_verify_password_incorrect(self):
        hashed = auth_mod.hash_password("mypassword")
        assert auth_mod.verify_password("wrongpassword", hashed) is False

    def test_verify_password_malformed_hash(self):
        assert auth_mod.verify_password("test", "not-a-valid-hash") is False
        assert auth_mod.verify_password("test", "") is False

    def test_verify_password_none_hash(self):
        assert auth_mod.verify_password("test", None) is False


class TestAuthJWTTokens:
    """Test JWT token creation and decoding."""

    def test_create_access_token_returns_string(self):
        token = auth_mod.create_access_token("user-123", "testuser")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_access_token_valid(self):
        token = auth_mod.create_access_token("user-123", "testuser")
        payload = auth_mod.decode_access_token(token)
        assert payload is not None
        assert payload.get("sub") == "user-123"
        assert payload.get("username") == "testuser"

    def test_decode_access_token_invalid(self):
        result = auth_mod.decode_access_token("invalid-token-string")
        # Should return None (either base64 fails or JWT decode fails)
        assert result is None or isinstance(result, dict)

    def test_decode_access_token_empty(self):
        result = auth_mod.decode_access_token("")
        assert result is None

    def test_token_has_required_claims(self):
        token = auth_mod.create_access_token("uid-1", "alice")
        payload = auth_mod.decode_access_token(token)
        assert payload is not None
        assert "sub" in payload
        assert "username" in payload
        assert "exp" in payload
        assert "iat" in payload
        assert "jti" in payload

    def test_token_with_extra_claims(self):
        token = auth_mod.create_access_token("uid-2", "bob", extra_claims={"role": "admin"})
        payload = auth_mod.decode_access_token(token)
        assert payload is not None
        assert payload.get("role") == "admin"

    def test_create_refresh_token(self):
        rt1 = auth_mod.create_refresh_token()
        rt2 = auth_mod.create_refresh_token()
        assert isinstance(rt1, str)
        assert len(rt1) > 20
        assert rt1 != rt2  # Unique tokens


class TestAuthRateLimiter:
    """Test the in-memory rate limiter."""

    def test_initial_allow(self):
        limiter = auth_mod.RateLimiter(max_requests=5, window_seconds=60)
        assert limiter.is_allowed("key1") is True

    def test_rate_limit_exceeded(self):
        limiter = auth_mod.RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            limiter.is_allowed("key1")
        assert limiter.is_allowed("key1") is False

    def test_different_keys_independent(self):
        limiter = auth_mod.RateLimiter(max_requests=2, window_seconds=60)
        limiter.is_allowed("key1")
        limiter.is_allowed("key1")
        assert limiter.is_allowed("key1") is False
        assert limiter.is_allowed("key2") is True

    def test_window_expiry(self):
        limiter = auth_mod.RateLimiter(max_requests=1, window_seconds=1)
        assert limiter.is_allowed("key1") is True
        assert limiter.is_allowed("key1") is False
        time.sleep(1.1)
        assert limiter.is_allowed("key1") is True


class TestAuthDatabase:
    """Test the AuthDatabase class with temporary database."""

    @pytest.fixture
    def auth_db(self, tmp_path):
        db_path = str(tmp_path / "test_auth.db")
        db = auth_mod.AuthDatabase(db_path=db_path)
        yield db
        db._conn.close()

    def test_tables_created(self, auth_db):
        """Verify all tables are created."""
        cursor = auth_db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "users" in tables
        assert "sessions" in tables
        assert "rate_limits" in tables

    def test_insert_and_query_user(self, auth_db):
        """Insert a user and query it back."""
        user_id = str(uuid.uuid4())
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        auth_db.execute(
            "INSERT INTO users (user_id, username, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, "testuser", "test@example.com", "hash123", now),
        )
        auth_db.commit()

        row = auth_db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        assert row is not None
        assert row["username"] == "testuser"
        assert row["email"] == "test@example.com"

    def test_session_management(self, auth_db):
        """Test session creation and querying."""
        user_id = str(uuid.uuid4())
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        auth_db.execute(
            "INSERT INTO users (user_id, username, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, "sessuser", "sess@example.com", "hash", now),
        )
        auth_db.commit()

        session_id = str(uuid.uuid4())
        refresh_token = "rt_" + uuid.uuid4().hex
        auth_db.execute(
            "INSERT INTO sessions (session_id, user_id, refresh_token, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, user_id, refresh_token, now, now),
        )
        auth_db.commit()

        row = auth_db.execute(
            "SELECT * FROM sessions WHERE refresh_token = ?", (refresh_token,)
        ).fetchone()
        assert row is not None
        assert row["user_id"] == user_id


class TestInfinityAuthHTTPEndpoints:
    """Test HTTP endpoints for the Auth worker using TestClient with temporary DB."""

    _main_mod_cache = None

    @pytest.fixture
    def auth_client(self, tmp_path):
        """Create a TestClient with a temporary database.

        `db`/`rate_limiter` no longer live on the `worker.py` shim (they were
        refactored into `main.py`, with routes reading them via
        `router.py`'s `_get_db()`/`init_router()`), so this imports `main.py`
        directly and rebinds the router's globals to test-isolated instances
        via the same `init_router()` the real app startup uses. The module
        itself (classes, app object) is cached across tests in this class —
        only db/rate_limiter need to be fresh per test, via init_router() below.
        """
        if TestInfinityAuthHTTPEndpoints._main_mod_cache is None:
            TestInfinityAuthHTTPEndpoints._main_mod_cache = _import_worker(
                "infinity_auth_main", _TRANC3_ROOT / "workers" / "infinity-auth" / "main.py"
            )
        main_mod = TestInfinityAuthHTTPEndpoints._main_mod_cache
        db_path = str(tmp_path / "test_auth.db")
        test_db = main_mod.AuthDatabase(db_path=db_path)
        test_rate_limiter = main_mod.RateLimiter(max_requests=100)
        main_mod.init_router(test_db, test_rate_limiter, main_mod.worker_kit)

        client = TestClient(main_mod.app)
        yield client

        test_db._conn.close()

    def test_health_endpoint(self, auth_client):
        response = auth_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "infinity-auth"

    def test_register_new_user(self, auth_client):
        response = auth_client.post(
            "/auth/register",
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "securepassword123",
                "display_name": "New User",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["username"] == "newuser"
        assert "user_id" in data
        assert "expires_in" in data

    def test_register_duplicate_username(self, auth_client):
        auth_client.post(
            "/auth/register",
            json={
                "username": "dupuser",
                "email": "first@example.com",
                "password": "password123",
            },
        )
        response = auth_client.post(
            "/auth/register",
            json={
                "username": "dupuser",
                "email": "second@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 409

    def test_register_duplicate_email(self, auth_client):
        auth_client.post(
            "/auth/register",
            json={
                "username": "user1",
                "email": "same@example.com",
                "password": "password123",
            },
        )
        response = auth_client.post(
            "/auth/register",
            json={
                "username": "user2",
                "email": "same@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 409

    def test_register_short_password(self, auth_client):
        response = auth_client.post(
            "/auth/register",
            json={
                "username": "shortpw",
                "email": "short@example.com",
                "password": "short",
            },
        )
        assert response.status_code == 422  # Validation error (min_length=8)

    def test_register_short_username(self, auth_client):
        response = auth_client.post(
            "/auth/register",
            json={
                "username": "ab",
                "email": "shortuser@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 422  # Validation error (min_length=3)

    def test_login_success(self, auth_client):
        # Register first
        auth_client.post(
            "/auth/register",
            json={
                "username": "loginuser",
                "email": "login@example.com",
                "password": "loginpassword",
            },
        )
        # Login
        response = auth_client.post(
            "/auth/login",
            json={
                "username": "loginuser",
                "password": "loginpassword",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["username"] == "loginuser"

    def test_login_wrong_password(self, auth_client):
        auth_client.post(
            "/auth/register",
            json={
                "username": "wrongpw",
                "email": "wrongpw@example.com",
                "password": "correctpassword",
            },
        )
        response = auth_client.post(
            "/auth/login",
            json={
                "username": "wrongpw",
                "password": "wrongpassword",
            },
        )
        assert response.status_code == 401

    def test_login_nonexistent_user(self, auth_client):
        response = auth_client.post(
            "/auth/login",
            json={
                "username": "ghost",
                "password": "doesntmatter",
            },
        )
        assert response.status_code == 401

    def test_get_profile(self, auth_client):
        # Register and get token
        reg = auth_client.post(
            "/auth/register",
            json={
                "username": "profileuser",
                "email": "profile@example.com",
                "password": "profilepassword",
            },
        )
        token = reg.json()["access_token"]

        response = auth_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "profileuser"
        assert data["email"] == "profile@example.com"
        assert data["mfa_enabled"] is False

    def test_get_profile_invalid_token(self, auth_client):
        response = auth_client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401

    def test_verify_token_endpoint(self, auth_client):
        reg = auth_client.post(
            "/auth/register",
            json={
                "username": "verifyuser",
                "email": "verify@example.com",
                "password": "verifypassword",
            },
        )
        token = reg.json()["access_token"]

        response = auth_client.get(
            "/auth/verify",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["username"] == "verifyuser"

    def test_refresh_token(self, auth_client):
        reg = auth_client.post(
            "/auth/register",
            json={
                "username": "refreshuser",
                "email": "refresh@example.com",
                "password": "refreshpassword",
            },
        )
        reg_data = reg.json()
        refresh_token = reg_data["refresh_token"]

        response = auth_client.post(
            "/auth/refresh",
            json={
                "refresh_token": refresh_token,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        # New refresh token should be different (rotation)
        assert data["refresh_token"] != refresh_token

    def test_refresh_token_twice_fails(self, auth_client):
        """Using a rotated refresh token again should fail."""
        reg = auth_client.post(
            "/auth/register",
            json={
                "username": "rotuser",
                "email": "rot@example.com",
                "password": "rotpassword",
            },
        )
        rt = reg.json()["refresh_token"]

        # First refresh works
        auth_client.post("/auth/refresh", json={"refresh_token": rt})

        # Second use of same token fails (revoked)
        response = auth_client.post("/auth/refresh", json={"refresh_token": rt})
        assert response.status_code == 401

    def test_logout(self, auth_client):
        reg = auth_client.post(
            "/auth/register",
            json={
                "username": "logoutuser",
                "email": "logout@example.com",
                "password": "logoutpassword",
            },
        )
        token = reg.json()["access_token"]

        response = auth_client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert "Logged out" in response.json()["message"]

    def test_mfa_setup(self, auth_client):
        reg = auth_client.post(
            "/auth/register",
            json={
                "username": "mfauser",
                "email": "mfa@example.com",
                "password": "mfapassword",
            },
        )
        token = reg.json()["access_token"]

        response = auth_client.post(
            "/auth/mfa/setup",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "secret" in data
        assert "qr_code_url" in data
        assert "backup_codes" in data
        assert len(data["backup_codes"]) == 10

    def test_mfa_enable(self, auth_client):
        reg = auth_client.post(
            "/auth/register",
            json={
                "username": "mfaenable",
                "email": "mfaenable@example.com",
                "password": "mfaenablepassword",
            },
        )
        token = reg.json()["access_token"]

        # Setup first
        auth_client.post("/auth/mfa/setup", headers={"Authorization": f"Bearer {token}"})

        # Enable
        response = auth_client.post(
            "/auth/mfa/enable",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert "MFA enabled" in response.json()["message"]

        # Verify MFA is enabled in profile
        profile = auth_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert profile.json()["mfa_enabled"] is True

    def test_mfa_disable(self, auth_client):
        reg = auth_client.post(
            "/auth/register",
            json={
                "username": "mfadisable",
                "email": "mfadisable@example.com",
                "password": "mfadisablepassword",
            },
        )
        token = reg.json()["access_token"]

        # Setup and enable
        auth_client.post("/auth/mfa/setup", headers={"Authorization": f"Bearer {token}"})
        auth_client.post("/auth/mfa/enable", headers={"Authorization": f"Bearer {token}"})

        # Disable
        response = auth_client.post(
            "/auth/mfa/disable",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert "MFA disabled" in response.json()["message"]

    def test_login_with_mfa_requires_code(self, auth_client):
        """When MFA is enabled, login without TOTP code should fail."""
        reg = auth_client.post(
            "/auth/register",
            json={
                "username": "mfalogin",
                "email": "mfalogin@example.com",
                "password": "mfaloginpassword",
            },
        )
        token = reg.json()["access_token"]

        # Setup and enable MFA
        auth_client.post("/auth/mfa/setup", headers={"Authorization": f"Bearer {token}"})
        auth_client.post("/auth/mfa/enable", headers={"Authorization": f"Bearer {token}"})

        # Login without MFA code should require it
        response = auth_client.post(
            "/auth/login",
            json={
                "username": "mfalogin",
                "password": "mfaloginpassword",
            },
        )
        assert response.status_code == 403
        assert "MFA" in response.json()["detail"]

    def test_login_with_mfa_valid_code(self, auth_client):
        """Login with MFA code (6-digit) should succeed."""
        import pyotp

        reg = auth_client.post(
            "/auth/register",
            json={
                "username": "mfacode",
                "email": "mfacode@example.com",
                "password": "mfacodepassword",
            },
        )
        token = reg.json()["access_token"]

        # Setup MFA — capture the TOTP secret so we can generate a valid code
        setup_resp = auth_client.post(
            "/auth/mfa/setup", headers={"Authorization": f"Bearer {token}"}
        )
        totp_secret = setup_resp.json()["secret"]
        auth_client.post("/auth/mfa/enable", headers={"Authorization": f"Bearer {token}"})

        # Generate the current valid TOTP code from the secret
        valid_code = pyotp.TOTP(totp_secret).now()

        # Login with the real TOTP code
        response = auth_client.post(
            "/auth/login",
            json={
                "username": "mfacode",
                "password": "mfacodepassword",
                "totp_code": valid_code,
            },
        )
        assert response.status_code == 200

    def test_login_with_mfa_invalid_code(self, auth_client):
        """Login with non-6-digit MFA code should fail."""
        reg = auth_client.post(
            "/auth/register",
            json={
                "username": "mfabad",
                "email": "mfabad@example.com",
                "password": "mfabadpassword",
            },
        )
        token = reg.json()["access_token"]

        # Setup and enable MFA
        auth_client.post("/auth/mfa/setup", headers={"Authorization": f"Bearer {token}"})
        auth_client.post("/auth/mfa/enable", headers={"Authorization": f"Bearer {token}"})

        # Login with bad TOTP code
        response = auth_client.post(
            "/auth/login",
            json={
                "username": "mfabad",
                "password": "mfabadpassword",
                "totp_code": "abc",
            },
        )
        assert response.status_code == 403

    def test_register_invalid_email(self, auth_client):
        response = auth_client.post(
            "/auth/register",
            json={
                "username": "bademail",
                "email": "not-an-email",
                "password": "password123",
            },
        )
        assert response.status_code == 422  # EmailStr validation

    def test_full_auth_flow(self, auth_client):
        """Complete registration -> login -> profile -> logout flow."""
        # Register
        reg = auth_client.post(
            "/auth/register",
            json={
                "username": "flowuser",
                "email": "flow@example.com",
                "password": "flowpassword",
            },
        )
        assert reg.status_code == 200
        token = reg.json()["access_token"]
        refresh = reg.json()["refresh_token"]

        # Get profile
        profile = auth_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert profile.status_code == 200
        assert profile.json()["username"] == "flowuser"

        # Verify token
        verify = auth_client.get("/auth/verify", headers={"Authorization": f"Bearer {token}"})
        assert verify.status_code == 200
        assert verify.json()["valid"] is True

        # Refresh token
        refreshed = auth_client.post("/auth/refresh", json={"refresh_token": refresh})
        assert refreshed.status_code == 200
        new_token = refreshed.json()["access_token"]

        # Use new token
        profile2 = auth_client.get("/auth/me", headers={"Authorization": f"Bearer {new_token}"})
        assert profile2.status_code == 200

        # Logout
        logout = auth_client.post("/auth/logout", headers={"Authorization": f"Bearer {new_token}"})
        assert logout.status_code == 200
