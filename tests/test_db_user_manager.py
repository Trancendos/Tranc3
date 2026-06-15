# FID: TRANC3-TEST-019 | Version: 1.1.0 | Module: auth
"""
tests/test_db_user_manager.py — Unit tests for DBUserManager.

Focuses on in-memory fallback behaviour (no live DB session required),
RBAC role propagation, and update_tier role-sync.  DB-backed paths are
covered by integration suites that provision a real SQLAlchemy session.

passlib 1.7.4 + bcrypt 5.0.0 have an incompatibility in the test environment
(hashpw() strict 72-byte limit).  All tests that exercise password hashing
patch pwd_context with lightweight fakes so the role/tier logic can be tested
independently of the cryptographic backend.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.auth.db_user_manager import _tier_to_roles

# ---------------------------------------------------------------------------
# Helpers — fake CryptContext that avoids bcrypt entirely
# ---------------------------------------------------------------------------


def _make_fake_pwd_context():
    """Return a MagicMock that behaves like a CryptContext."""
    ctx = MagicMock()
    ctx.hash.side_effect = lambda pw: f"hashed:{pw}"
    ctx.verify.side_effect = lambda pw, hashed: hashed == f"hashed:{pw}"
    return ctx


def _make_manager():
    """
    Return a DBUserManager (fallback-only) with pwd_context patched.

    The patch targets the module-level ``pwd_context`` used inside
    ``src.auth.db_user_manager`` so that all methods use the fake.
    """
    from src.auth.db_user_manager import DBUserManager

    fake_ctx = _make_fake_pwd_context()
    mgr = DBUserManager(db_session_factory=None)
    mgr._pwd_context = fake_ctx  # store for introspection if needed
    # Patch module-level pwd_context used by create_user / authenticate_user
    with patch("src.auth.db_user_manager.pwd_context", fake_ctx):
        yield mgr


# ---------------------------------------------------------------------------
# _tier_to_roles helper (no I/O — runs without any patching)
# ---------------------------------------------------------------------------


class TestTierToRoles:
    def test_free_maps_to_user(self):
        assert _tier_to_roles("free") == ["user"]

    def test_pro_maps_to_operator(self):
        assert _tier_to_roles("pro") == ["operator"]

    def test_business_maps_to_operator(self):
        assert _tier_to_roles("business") == ["operator"]

    def test_enterprise_maps_to_admin(self):
        assert _tier_to_roles("enterprise") == ["admin"]

    def test_admin_maps_to_admin(self):
        assert _tier_to_roles("admin") == ["admin"]

    def test_unknown_tier_defaults_to_user(self):
        assert _tier_to_roles("mystery") == ["user"]

    def test_empty_tier_defaults_to_user(self):
        assert _tier_to_roles("") == ["user"]

    def test_returns_list(self):
        result = _tier_to_roles("free")
        assert isinstance(result, list)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# DBUserManager — in-memory fallback tests (pwd_context patched)
# ---------------------------------------------------------------------------


@pytest.fixture()
def mgr(monkeypatch):
    """DBUserManager in fallback mode with pwd_context mocked."""
    from src.auth.db_user_manager import DBUserManager

    fake_ctx = _make_fake_pwd_context()
    monkeypatch.setattr("src.auth.db_user_manager.pwd_context", fake_ctx)
    return DBUserManager(db_session_factory=None)


class TestDBUserManagerFallbackCreate:
    def test_create_user_returns_dict(self, mgr):
        result = mgr.create_user("alice", "Password1")
        assert isinstance(result, dict)

    def test_create_user_returns_username(self, mgr):
        result = mgr.create_user("bob", "Password1")
        assert result["username"] == "bob"

    def test_create_user_returns_user_id(self, mgr):
        result = mgr.create_user("carol", "Password1")
        assert "user_id" in result

    def test_create_user_default_tier_free(self, mgr):
        result = mgr.create_user("dave", "Password1")
        assert result["tier"] == "free"

    def test_create_user_duplicate_raises(self, mgr):
        from fastapi import HTTPException

        mgr.create_user("eve", "Password1")
        with pytest.raises(HTTPException) as exc_info:
            mgr.create_user("eve", "Password1")
        assert exc_info.value.status_code == 400

    def test_create_user_sets_roles(self, mgr):
        mgr.create_user("frank", "Password1")
        user = mgr.get_user("frank")
        assert "roles" in user
        assert user["roles"] == ["user"]  # free tier → user role


class TestDBUserManagerFallbackAuthenticate:
    def test_authenticate_valid(self, mgr):
        mgr.create_user("grace", "Password1")
        result = mgr.authenticate_user("grace", "Password1")
        assert result is not None
        assert result["username"] == "grace"

    def test_authenticate_wrong_password_returns_none(self, mgr):
        mgr.create_user("henry", "Password1")
        result = mgr.authenticate_user("henry", "WrongPass9")
        assert result is None

    def test_authenticate_unknown_user_returns_none(self, mgr):
        result = mgr.authenticate_user("nobody", "Password1")
        assert result is None


class TestDBUserManagerFallbackGetUser:
    def test_get_user_returns_user(self, mgr):
        mgr.create_user("ida", "Password1")
        user = mgr.get_user("ida")
        assert user is not None
        assert user["username"] == "ida"

    def test_get_user_nonexistent_returns_none(self, mgr):
        assert mgr.get_user("ghost") is None

    def test_get_user_includes_roles(self, mgr):
        mgr.create_user("james", "Password1")
        user = mgr.get_user("james")
        assert "roles" in user

    def test_get_user_backfills_missing_roles(self, mgr):
        """Users created before role propagation should get roles backfilled."""
        mgr._fallback["legacy"] = {
            "id": "x",
            "username": "legacy",
            "hashed_password": "hashed:placeholder",
            "tier": "pro",
            "is_active": True,
        }
        user = mgr.get_user("legacy")
        assert user["roles"] == ["operator"]

    def test_get_user_backfills_roles_for_free_tier(self, mgr):
        mgr._fallback["olduser"] = {
            "id": "y",
            "username": "olduser",
            "hashed_password": "hashed:placeholder",
            "tier": "free",
            "is_active": True,
        }
        user = mgr.get_user("olduser")
        assert user["roles"] == ["user"]


# ---------------------------------------------------------------------------
# update_tier role-sync (the primary new behaviour)
# ---------------------------------------------------------------------------


class TestUpdateTierRoleSync:
    def test_update_tier_returns_true_for_existing_user(self, mgr):
        mgr.create_user("kate", "Password1")
        result = mgr.update_tier("kate", "pro")
        assert result is True

    def test_update_tier_returns_false_for_nonexistent_user(self, mgr):
        result = mgr.update_tier("nobody", "pro")
        assert result is False

    def test_update_tier_updates_tier_field(self, mgr):
        mgr.create_user("liam", "Password1")
        mgr.update_tier("liam", "pro")
        user = mgr.get_user("liam")
        assert user["tier"] == "pro"

    def test_update_tier_syncs_roles_free_to_pro(self, mgr):
        mgr.create_user("mia", "Password1")
        user = mgr.get_user("mia")
        assert user["roles"] == ["user"]
        mgr.update_tier("mia", "pro")
        user = mgr.get_user("mia")
        assert user["roles"] == ["operator"]

    def test_update_tier_syncs_roles_to_business(self, mgr):
        mgr.create_user("noah", "Password1")
        mgr.update_tier("noah", "business")
        user = mgr.get_user("noah")
        assert user["roles"] == ["operator"]

    def test_update_tier_syncs_roles_to_enterprise(self, mgr):
        mgr.create_user("olivia", "Password1")
        mgr.update_tier("olivia", "enterprise")
        user = mgr.get_user("olivia")
        assert user["roles"] == ["admin"]

    def test_update_tier_syncs_roles_to_admin(self, mgr):
        mgr.create_user("peter", "Password1")
        mgr.update_tier("peter", "admin")
        user = mgr.get_user("peter")
        assert user["roles"] == ["admin"]

    def test_update_tier_downgrade_resets_roles(self, mgr):
        """Downgrading from enterprise to free must revoke admin role."""
        mgr.create_user("quinn", "Password1")
        mgr.update_tier("quinn", "enterprise")
        user = mgr.get_user("quinn")
        assert user["roles"] == ["admin"]
        mgr.update_tier("quinn", "free")
        user = mgr.get_user("quinn")
        assert user["roles"] == ["user"]

    def test_update_tier_multiple_upgrades_idempotent(self, mgr):
        mgr.create_user("rosa", "Password1")
        mgr.update_tier("rosa", "pro")
        mgr.update_tier("rosa", "pro")
        user = mgr.get_user("rosa")
        assert user["roles"] == ["operator"]

    def test_update_tier_unknown_new_tier_defaults_to_user_role(self, mgr):
        mgr.create_user("sam", "Password1")
        mgr.update_tier("sam", "mystery_tier")
        user = mgr.get_user("sam")
        assert user["roles"] == ["user"]


# ---------------------------------------------------------------------------
# Password validation (tests the _validate_password logic — NOT bcrypt hashing)
# ---------------------------------------------------------------------------


class TestPasswordValidation:
    """_validate_password raises BEFORE any bcrypt call so no patch needed."""

    def test_too_short_rejected(self):
        from fastapi import HTTPException

        from src.auth.db_user_manager import DBUserManager

        fake_ctx = _make_fake_pwd_context()
        with patch("src.auth.db_user_manager.pwd_context", fake_ctx):
            mgr = DBUserManager(db_session_factory=None)
            with pytest.raises(HTTPException) as exc_info:
                mgr.create_user("u1", "Abc1")
        assert exc_info.value.status_code == 400
        assert "8 characters" in exc_info.value.detail

    def test_no_uppercase_rejected(self):
        from fastapi import HTTPException

        from src.auth.db_user_manager import DBUserManager

        fake_ctx = _make_fake_pwd_context()
        with patch("src.auth.db_user_manager.pwd_context", fake_ctx):
            mgr = DBUserManager(db_session_factory=None)
            with pytest.raises(HTTPException) as exc_info:
                mgr.create_user("u2", "password1")
        assert exc_info.value.status_code == 400

    def test_no_digit_rejected(self):
        from fastapi import HTTPException

        from src.auth.db_user_manager import DBUserManager

        fake_ctx = _make_fake_pwd_context()
        with patch("src.auth.db_user_manager.pwd_context", fake_ctx):
            mgr = DBUserManager(db_session_factory=None)
            with pytest.raises(HTTPException) as exc_info:
                mgr.create_user("u3", "Passwordonly")
        assert exc_info.value.status_code == 400

    def test_valid_password_accepted(self):
        from src.auth.db_user_manager import DBUserManager

        fake_ctx = _make_fake_pwd_context()
        with patch("src.auth.db_user_manager.pwd_context", fake_ctx):
            mgr = DBUserManager(db_session_factory=None)
            result = mgr.create_user("u4", "Password1")
        assert result["username"] == "u4"
