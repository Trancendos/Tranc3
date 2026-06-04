# tests/test_devocity.py — Tests for src/devocity/portal.py
"""Comprehensive tests for the DevOcity developer portal."""

from __future__ import annotations

import hashlib

from src.devocity.portal import (
    ApiKey,
    ApiKeyScope,
    DevAccountStatus,
    DeveloperAccount,
    DevOcity,
    WebhookEndpoint,
    get_devocity,
)

# ── Enum tests ──────────────────────────────────────────────────────────────


class TestDevAccountStatus:
    def test_values(self):
        assert DevAccountStatus.ACTIVE == "active"
        assert DevAccountStatus.SUSPENDED == "suspended"
        assert DevAccountStatus.SANDBOX == "sandbox"


class TestApiKeyScope:
    def test_values(self):
        assert ApiKeyScope.READ == "read"
        assert ApiKeyScope.WRITE == "write"
        assert ApiKeyScope.ADMIN == "admin"
        assert ApiKeyScope.SPARK == "spark"
        assert ApiKeyScope.GRID == "grid"
        assert ApiKeyScope.FULL == "full"


# ── ApiKey tests ────────────────────────────────────────────────────────────


class TestApiKey:
    def test_defaults(self):
        key = ApiKey()
        assert key.id != ""
        assert key.developer_id == ""
        assert key.name == ""
        assert key.key_prefix == ""
        assert key.key_hash == ""
        assert key.scopes == []
        assert key.created_at > 0
        assert key.last_used is None
        assert key.revoked is False
        assert key.request_count == 0

    def test_to_dict(self):
        key = ApiKey(
            developer_id="dev-1",
            name="test-key",
            key_prefix="trx_abc1",
            scopes=[ApiKeyScope.READ, ApiKeyScope.WRITE],
        )
        d = key.to_dict()
        assert d["name"] == "test-key"
        assert d["key_prefix"] == "trx_abc1****"
        assert d["scopes"] == ["read", "write"]
        assert d["revoked"] is False


# ── WebhookEndpoint tests ──────────────────────────────────────────────────


class TestWebhookEndpoint:
    def test_defaults(self):
        wh = WebhookEndpoint()
        assert wh.id != ""
        assert wh.developer_id == ""
        assert wh.url == ""
        assert wh.events == []
        assert wh.secret != ""  # Auto-generated
        assert wh.active is True
        assert wh.created_at > 0
        assert wh.delivery_count == 0
        assert wh.failure_count == 0

    def test_to_dict(self):
        wh = WebhookEndpoint(
            developer_id="dev-1",
            url="https://example.com/webhook",
            events=["deploy.success"],
        )
        d = wh.to_dict()
        assert d["url"] == "https://example.com/webhook"
        assert d["events"] == ["deploy.success"]
        assert d["active"] is True


# ── DeveloperAccount tests ─────────────────────────────────────────────────


class TestDeveloperAccount:
    def test_defaults(self):
        acct = DeveloperAccount()
        assert acct.id != ""
        assert acct.user_id == ""
        assert acct.display_name == ""
        assert acct.status == DevAccountStatus.ACTIVE
        assert acct.api_keys == []
        assert acct.webhooks == []
        assert acct.usage == {}

    def test_to_dict(self):
        acct = DeveloperAccount(user_id="user-1", display_name="Alice")
        d = acct.to_dict()
        assert d["user_id"] == "user-1"
        assert d["display_name"] == "Alice"
        assert d["status"] == "active"
        assert d["api_key_count"] == 0
        assert d["webhook_count"] == 0

    def test_to_dict_counts_active_keys(self):
        acct = DeveloperAccount()
        acct.api_keys.append(ApiKey(name="active-key", revoked=False))
        acct.api_keys.append(ApiKey(name="revoked-key", revoked=True))
        d = acct.to_dict()
        assert d["api_key_count"] == 1

    def test_to_dict_counts_active_webhooks(self):
        acct = DeveloperAccount()
        acct.webhooks.append(WebhookEndpoint(url="https://a.com", active=True))
        acct.webhooks.append(WebhookEndpoint(url="https://b.com", active=False))
        d = acct.to_dict()
        assert d["webhook_count"] == 1


# ── DevOcity engine tests ──────────────────────────────────────────────────


class TestDevOcity:
    def setup_method(self):
        self.dev = DevOcity()

    # ── Account management ──────────────────────────────────────────────

    def test_create_account(self):
        acct = self.dev.create_account("user-1", "Alice")
        assert acct.user_id == "user-1"
        assert acct.display_name == "Alice"
        assert acct.status == DevAccountStatus.ACTIVE

    def test_get_account(self):
        acct = self.dev.create_account("user-1", "Alice")
        retrieved = self.dev.get_account(acct.id)
        assert retrieved is acct

    def test_get_account_not_found(self):
        assert self.dev.get_account("nonexistent") is None

    def test_get_account_by_user(self):
        self.dev.create_account("user-1", "Alice")
        self.dev.create_account("user-2", "Bob")
        acct = self.dev.get_account_by_user("user-1")
        assert acct is not None
        assert acct.display_name == "Alice"

    def test_get_account_by_user_not_found(self):
        assert self.dev.get_account_by_user("nonexistent") is None

    # ── API Key management ──────────────────────────────────────────────

    def test_issue_api_key(self):
        acct = self.dev.create_account("user-1", "Alice")
        result = self.dev.issue_api_key(acct.id, "my-key")
        assert result is not None
        plain, api_key = result
        assert plain.startswith("trx_")
        assert len(plain) > 10
        assert api_key.name == "my-key"
        assert api_key.key_prefix == plain[:8]
        assert api_key.key_hash != ""

    def test_issue_api_key_hash_is_sha256(self):
        acct = self.dev.create_account("user-1", "Alice")
        plain, api_key = self.dev.issue_api_key(acct.id, "test")
        expected_hash = hashlib.sha256(plain.encode()).hexdigest()
        assert api_key.key_hash == expected_hash

    def test_issue_api_key_default_scope(self):
        acct = self.dev.create_account("user-1", "Alice")
        _, api_key = self.dev.issue_api_key(acct.id, "test")
        assert api_key.scopes == [ApiKeyScope.READ]

    def test_issue_api_key_custom_scopes(self):
        acct = self.dev.create_account("user-1", "Alice")
        _, api_key = self.dev.issue_api_key(
            acct.id,
            "admin-key",
            scopes=[ApiKeyScope.ADMIN, ApiKeyScope.SPARK],
        )
        assert ApiKeyScope.ADMIN in api_key.scopes
        assert ApiKeyScope.SPARK in api_key.scopes

    def test_issue_api_key_nonexistent_account(self):
        result = self.dev.issue_api_key("nonexistent", "test")
        assert result is None

    def test_revoke_api_key(self):
        acct = self.dev.create_account("user-1", "Alice")
        _, api_key = self.dev.issue_api_key(acct.id, "test")
        assert self.dev.revoke_api_key(acct.id, api_key.id)
        assert api_key.revoked is True

    def test_revoke_api_key_wrong_account(self):
        acct1 = self.dev.create_account("user-1", "Alice")
        acct2 = self.dev.create_account("user-2", "Bob")
        _, api_key = self.dev.issue_api_key(acct1.id, "test")
        assert not self.dev.revoke_api_key(acct2.id, api_key.id)

    def test_revoke_api_key_nonexistent_key(self):
        acct = self.dev.create_account("user-1", "Alice")
        assert not self.dev.revoke_api_key(acct.id, "nonexistent")

    def test_revoke_api_key_nonexistent_account(self):
        assert not self.dev.revoke_api_key("nonexistent", "nonexistent")

    def test_multiple_api_keys(self):
        acct = self.dev.create_account("user-1", "Alice")
        self.dev.issue_api_key(acct.id, "key-1")
        self.dev.issue_api_key(acct.id, "key-2")
        assert len(acct.api_keys) == 2

    # ── Webhook management ──────────────────────────────────────────────

    def test_register_webhook(self):
        acct = self.dev.create_account("user-1", "Alice")
        wh = self.dev.register_webhook(
            acct.id,
            "https://example.com/hook",
            ["deploy.success", "deploy.failure"],
        )
        assert wh is not None
        assert wh.url == "https://example.com/hook"
        assert wh.events == ["deploy.success", "deploy.failure"]
        assert wh.active is True

    def test_register_webhook_nonexistent_account(self):
        result = self.dev.register_webhook("nonexistent", "https://example.com/hook", ["event"])
        assert result is None

    def test_webhook_attached_to_account(self):
        acct = self.dev.create_account("user-1", "Alice")
        self.dev.register_webhook(acct.id, "https://example.com/hook", ["event"])
        assert len(acct.webhooks) == 1

    # ── Guides ──────────────────────────────────────────────────────────

    def test_guides(self):
        guides = self.dev.guides()
        assert len(guides) >= 4
        assert all("id" in g for g in guides)
        assert all("title" in g for g in guides)

    # ── Stats ───────────────────────────────────────────────────────────

    def test_stats_empty(self):
        stats = self.dev.stats()
        assert stats["service"] == "devocity"
        assert stats["total_accounts"] == 0
        assert stats["total_active_keys"] == 0

    def test_stats_populated(self):
        acct = self.dev.create_account("user-1", "Alice")
        self.dev.issue_api_key(acct.id, "key-1")
        self.dev.issue_api_key(acct.id, "key-2")
        stats = self.dev.stats()
        assert stats["total_accounts"] == 1
        assert stats["total_active_keys"] == 2

    def test_stats_revoked_keys_not_counted(self):
        acct = self.dev.create_account("user-1", "Alice")
        _, api_key = self.dev.issue_api_key(acct.id, "key-1")
        self.dev.revoke_api_key(acct.id, api_key.id)
        stats = self.dev.stats()
        assert stats["total_active_keys"] == 0


# ── Module-level singleton tests ────────────────────────────────────────────


class TestModuleSingleton:
    def test_get_devocity_singleton(self):
        d1 = get_devocity()
        d2 = get_devocity()
        assert d1 is d2
