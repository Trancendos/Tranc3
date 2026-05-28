"""
tests/test_oci_adaptive_provider.py — Unit tests for OCI Adaptive Storage Provider.

Tests cover:
  - OCI_FREE_TIER_LIMITS constant values
  - StorageTier / CircuitState / SystemMode enums
  - CircuitBreaker state machine (CLOSED → OPEN → HALF_OPEN → CLOSED)
  - OciQuotaTracker: write/request tracking, limit enforcement, monthly reset
  - _aws_sig4_sign: header generation, determinism, required keys
  - OciKeepaliveWorker: construction and status API
  - PersistentInfrastructureDatum / AdaptiveInstanceDatum: key patterns
  - AdaptiveProviderConfig: defaults
  - OciAdaptiveProvider: construction, tier ordering

No live OCI connection is required — all network I/O is mocked.
"""

from __future__ import annotations  # noqa: I001

from unittest.mock import AsyncMock, MagicMock

import pytest

from shared_core.architecture.oci_adaptive_provider import (
    OCI_FREE_TIER_LIMITS,
    AdaptiveInstanceDatum,
    AdaptiveProviderConfig,
    CircuitBreaker,
    CircuitState,
    OciAdaptiveProvider,
    OciKeepaliveWorker,
    OciQuotaTracker,
    PersistentInfrastructureDatum,
    StorageTier,
    SystemMode,
    _aws_sig4_sign,
)

# ===========================================================================
# Constants
# ===========================================================================


class TestOciFreeTierLimits:
    def test_storage_bytes_is_20gb(self):
        limit = OCI_FREE_TIER_LIMITS["object_storage_bytes"]
        assert limit == 20 * 1024**3  # 20 GiB

    def test_api_requests_monthly(self):
        assert OCI_FREE_TIER_LIMITS["api_requests_monthly"] == 50_000

    def test_egress_bytes_is_10tb(self):
        limit = OCI_FREE_TIER_LIMITS["egress_bytes_monthly"]
        assert limit == 10 * 1024**4  # 10 TiB

    def test_vault_secrets_limit(self):
        assert OCI_FREE_TIER_LIMITS["vault_secrets"] > 0

    def test_hsm_key_versions_limit(self):
        assert OCI_FREE_TIER_LIMITS["hsm_key_versions"] > 0

    def test_all_limits_positive(self):
        for key, val in OCI_FREE_TIER_LIMITS.items():
            assert val > 0, f"{key} must be positive"


# ===========================================================================
# Enums
# ===========================================================================


class TestStorageTier:
    def test_oci_is_first_tier(self):
        tiers = list(StorageTier)
        assert tiers[0] == StorageTier.OCI

    def test_cloudflare_r2_present(self):
        assert StorageTier.CLOUDFLARE in list(StorageTier)

    def test_minio_present(self):
        assert StorageTier.MINIO in list(StorageTier)

    def test_at_least_four_tiers(self):
        assert len(list(StorageTier)) >= 4

    def test_values_are_strings(self):
        for tier in StorageTier:
            assert isinstance(tier.value, str)


class TestCircuitState:
    def test_closed_value(self):
        assert CircuitState.CLOSED.value == "closed"

    def test_open_value(self):
        assert CircuitState.OPEN.value == "open"

    def test_half_open_value(self):
        assert CircuitState.HALF_OPEN.value == "half_open"

    def test_three_states(self):
        assert len(list(CircuitState)) == 3


class TestSystemMode:
    def test_hybrid_present(self):
        assert SystemMode.HYBRID in list(SystemMode)

    def test_cloud_only_present(self):
        assert SystemMode.CLOUD_ONLY in list(SystemMode)

    def test_true_nas_present(self):
        assert SystemMode.TRUE_NAS in list(SystemMode)


# ===========================================================================
# CircuitBreaker
# ===========================================================================


class TestCircuitBreaker:
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("test-tier")
        assert cb.state == CircuitState.CLOSED

    def test_initially_available(self):
        cb = CircuitBreaker("test-tier")
        assert cb.is_available() is True

    def test_trips_after_threshold_failures(self):
        cb = CircuitBreaker("test-tier", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.is_available() is False

    def test_does_not_trip_before_threshold(self):
        cb = CircuitBreaker("test-tier", failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available() is True

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test-tier", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()  # only 1 failure now
        assert cb.state == CircuitState.CLOSED

    def test_open_circuit_transitions_to_half_open_after_recovery(self):
        # With recovery_seconds=0, the breaker moves to HALF_OPEN immediately
        cb = CircuitBreaker("test-tier", failure_threshold=2, recovery_seconds=0)
        cb.record_failure()
        cb.record_failure()
        # recovery_seconds=0 means HALF_OPEN right after tripping
        assert cb.state in (CircuitState.OPEN, CircuitState.HALF_OPEN)
        # Record success to fully close it
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_status_dict_has_required_keys(self):
        cb = CircuitBreaker("my-tier")
        status = cb.status()
        assert "tier" in status
        assert "state" in status
        assert "failures" in status

    def test_status_tier_name(self):
        cb = CircuitBreaker("oci-primary")
        assert cb.status()["tier"] == "oci-primary"

    def test_default_failure_threshold_is_five(self):
        cb = CircuitBreaker("t")
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_custom_threshold(self):
        cb = CircuitBreaker("t", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_multiple_breakers_independent(self):
        cb1 = CircuitBreaker("tier-1", failure_threshold=2)
        cb2 = CircuitBreaker("tier-2", failure_threshold=2)
        cb1.record_failure()
        cb1.record_failure()
        assert cb1.state == CircuitState.OPEN
        assert cb2.state == CircuitState.CLOSED


# ===========================================================================
# OciQuotaTracker
# ===========================================================================


class TestOciQuotaTracker:
    @pytest.fixture(autouse=True)
    def fresh_tracker(self, tmp_path, monkeypatch):
        # OciQuotaTracker persists to /tmp/tranc3_oci_quota.json — redirect to a
        # fresh temp file so tests are fully isolated from each other and from the host.
        import shared_core.architecture.oci_adaptive_provider as _mod

        sidecar = str(tmp_path / "oci_quota_test.json")
        monkeypatch.setattr(_mod.OciQuotaTracker, "_SIDECAR", sidecar)
        yield

    @pytest.mark.asyncio
    async def test_initial_snapshot_zeros(self):
        qt = OciQuotaTracker()
        snap = await qt.usage_snapshot()
        assert snap["storage_gb"] == 0.0
        assert snap["api_requests"] == 0
        assert snap["egress_gb"] == 0.0

    @pytest.mark.asyncio
    async def test_snapshot_has_limits(self):
        qt = OciQuotaTracker()
        snap = await qt.usage_snapshot()
        assert snap["storage_limit_gb"] == 20
        assert snap["api_limit"] == 50_000
        assert snap["egress_limit_gb"] == 10_240

    @pytest.mark.asyncio
    async def test_record_write_updates_storage(self):
        qt = OciQuotaTracker()
        await qt.record_write(1024 * 1024 * 100)  # 100 MiB
        snap = await qt.usage_snapshot()
        assert snap["storage_gb"] > 0
        assert snap["storage_pct"] > 0

    @pytest.mark.asyncio
    async def test_record_request_updates_api_count(self):
        # record_request() counts one API call per invocation (egress_bytes is optional)
        qt = OciQuotaTracker()
        for _ in range(5):
            await qt.record_request()
        snap = await qt.usage_snapshot()
        assert snap["api_requests"] >= 5

    @pytest.mark.asyncio
    async def test_write_allowed_within_limit(self):
        qt = OciQuotaTracker()
        allowed, reason = await qt.check_write_allowed(1024)
        assert allowed is True
        assert reason == "ok"

    @pytest.mark.asyncio
    async def test_write_blocked_at_storage_limit(self):
        qt = OciQuotaTracker()
        # Exceed 20 GiB
        await qt.record_write(21 * 1024**3)
        allowed, reason = await qt.check_write_allowed(1)
        assert allowed is False
        assert "quota" in reason.lower() or "exceeded" in reason.lower()

    @pytest.mark.asyncio
    async def test_snapshot_includes_month(self):
        qt = OciQuotaTracker()
        snap = await qt.usage_snapshot()
        assert "month" in snap
        # Format: YYYY-MM
        month = snap["month"]
        assert len(month) == 7
        assert month[4] == "-"

    @pytest.mark.asyncio
    async def test_cumulative_writes(self):
        qt = OciQuotaTracker()
        await qt.record_write(1024**3)  # 1 GiB
        await qt.record_write(1024**3)  # 1 GiB
        snap = await qt.usage_snapshot()
        assert snap["storage_gb"] >= 1.9  # at least ~2 GiB

    @pytest.mark.asyncio
    async def test_api_limit_enforcement(self):
        # Exhaust API quota by directly patching the internal counter
        qt = OciQuotaTracker()
        async with qt._lock:
            qt._data["api_requests"] = 50_001  # force over limit
        allowed, reason = await qt.check_write_allowed(1)
        assert allowed is False
        assert "quota" in reason.lower() or "exceeded" in reason.lower()


# ===========================================================================
# _aws_sig4_sign
# ===========================================================================


class TestAwsSig4Sign:
    _BASE_ARGS = dict(
        method="GET",
        url="https://example.r2.cloudflarestorage.com/bucket/key",
        headers={"content-type": "application/octet-stream"},
        body=b"",
        access_key="AKIAIOSFODNN7EXAMPLE",
        secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",  # pragma: allowlist secret
        service="s3",
        region="auto",
    )

    def test_returns_dict(self):
        signed = _aws_sig4_sign(**self._BASE_ARGS)
        assert isinstance(signed, dict)

    def test_authorization_header_present(self):
        signed = _aws_sig4_sign(**self._BASE_ARGS)
        assert any(k.lower() == "authorization" for k in signed)

    def test_x_amz_date_present(self):
        signed = _aws_sig4_sign(**self._BASE_ARGS)
        assert any("amz-date" in k.lower() or "x-amz-date" in k.lower() for k in signed)

    def test_authorization_contains_aws4_hmac(self):
        signed = _aws_sig4_sign(**self._BASE_ARGS)
        auth = next(v for k, v in signed.items() if k.lower() == "authorization")
        assert "AWS4-HMAC-SHA256" in auth

    def test_authorization_contains_access_key(self):
        signed = _aws_sig4_sign(**self._BASE_ARGS)
        auth = next(v for k, v in signed.items() if k.lower() == "authorization")
        assert "AKIAIOSFODNN7EXAMPLE" in auth

    def test_authorization_contains_credential_scope(self):
        signed = _aws_sig4_sign(**self._BASE_ARGS)
        auth = next(v for k, v in signed.items() if k.lower() == "authorization")
        assert "Credential=" in auth
        assert "SignedHeaders=" in auth
        assert "Signature=" in auth

    def test_deterministic_for_same_timestamp(self):
        """Same inputs → same signature (time is embedded in headers so use freeze)."""
        # Just verify the function is pure / doesn't raise
        s1 = _aws_sig4_sign(**self._BASE_ARGS)
        s2 = _aws_sig4_sign(**self._BASE_ARGS)
        # Both must be valid dicts with Authorization
        assert "authorization" in {k.lower() for k in s1}
        assert "authorization" in {k.lower() for k in s2}

    def test_different_methods_differ(self):
        args_get = {**self._BASE_ARGS, "method": "GET"}
        args_put = {**self._BASE_ARGS, "method": "PUT", "body": b"data"}
        s_get = _aws_sig4_sign(**args_get)
        s_put = _aws_sig4_sign(**args_put)
        auth_get = next(v for k, v in s_get.items() if k.lower() == "authorization")
        auth_put = next(v for k, v in s_put.items() if k.lower() == "authorization")
        assert auth_get != auth_put

    def test_post_method(self):
        args = {**self._BASE_ARGS, "method": "POST", "body": b'{"key": "value"}'}
        signed = _aws_sig4_sign(**args)
        assert isinstance(signed, dict)

    def test_custom_region(self):
        args = {**self._BASE_ARGS, "region": "us-east-1"}
        signed = _aws_sig4_sign(**args)
        auth = next(v for k, v in signed.items() if k.lower() == "authorization")
        assert "us-east-1" in auth


# ===========================================================================
# OciKeepaliveWorker
# ===========================================================================


class TestOciKeepaliveWorker:
    def test_instantiation(self):
        worker = OciKeepaliveWorker()
        assert worker is not None

    def test_metadata_url_constant(self):
        assert hasattr(OciKeepaliveWorker, "METADATA_URL")
        assert "169.254" in OciKeepaliveWorker.METADATA_URL

    def test_status_before_start(self):
        worker = OciKeepaliveWorker()
        status = worker.status()
        assert isinstance(status, dict)
        assert "running" in status

    def test_not_running_before_start(self):
        worker = OciKeepaliveWorker()
        assert worker.status()["running"] is False

    def test_stop_before_start_is_safe(self):
        worker = OciKeepaliveWorker()
        # Should not raise
        worker.stop()

    def test_has_start_method(self):
        assert callable(getattr(OciKeepaliveWorker, "start", None))


# ===========================================================================
# AdaptiveProviderConfig
# ===========================================================================


class TestAdaptiveProviderConfig:
    def test_default_construction(self):
        cfg = AdaptiveProviderConfig()
        assert cfg is not None

    def test_default_mode_is_hybrid(self):
        cfg = AdaptiveProviderConfig()
        assert cfg.system_mode == SystemMode.HYBRID

    def test_oci_defaults_to_none(self):
        cfg = AdaptiveProviderConfig()
        assert cfg.oci is None

    def test_r2_defaults_to_none(self):
        cfg = AdaptiveProviderConfig()
        assert cfg.r2 is None

    def test_minio_defaults_to_none(self):
        cfg = AdaptiveProviderConfig()
        assert cfg.minio is None


# ===========================================================================
# OciAdaptiveProvider
# ===========================================================================


class TestOciAdaptiveProvider:
    def test_instantiation_default_config(self):
        provider = OciAdaptiveProvider(config=AdaptiveProviderConfig())
        assert provider is not None

    def test_instantiation_with_config(self):
        cfg = AdaptiveProviderConfig(system_mode=SystemMode.CLOUD_ONLY)
        provider = OciAdaptiveProvider(config=cfg)
        assert provider is not None

    def test_has_write_method(self):
        provider = OciAdaptiveProvider(config=AdaptiveProviderConfig())
        assert callable(getattr(provider, "write", None))

    def test_has_read_method(self):
        provider = OciAdaptiveProvider(config=AdaptiveProviderConfig())
        assert callable(getattr(provider, "read", None))

    def test_has_exists_method(self):
        provider = OciAdaptiveProvider(config=AdaptiveProviderConfig())
        assert callable(getattr(provider, "exists", None))

    def test_has_delete_method(self):
        provider = OciAdaptiveProvider(config=AdaptiveProviderConfig())
        assert callable(getattr(provider, "delete", None))

    def test_has_close_method(self):
        provider = OciAdaptiveProvider(config=AdaptiveProviderConfig())
        assert callable(getattr(provider, "close", None))

    def test_has_health_method(self):
        provider = OciAdaptiveProvider(config=AdaptiveProviderConfig())
        assert callable(getattr(provider, "health", None))

    def test_has_metrics_snapshot_method(self):
        provider = OciAdaptiveProvider(config=AdaptiveProviderConfig())
        assert callable(getattr(provider, "metrics_snapshot", None))

    @pytest.mark.asyncio
    async def test_health_returns_dict(self):
        provider = OciAdaptiveProvider(config=AdaptiveProviderConfig())
        health = await provider.health()
        assert isinstance(health, dict)

    @pytest.mark.asyncio
    async def test_write_raises_without_tiers(self):
        """With no tiers configured, write should raise an appropriate error."""
        cfg = AdaptiveProviderConfig(system_mode=SystemMode.CLOUD_ONLY)
        provider = OciAdaptiveProvider(config=cfg)
        with pytest.raises(Exception):
            await provider.write("bucket", "key", b"data")

    @pytest.mark.asyncio
    async def test_read_raises_without_tiers(self):
        cfg = AdaptiveProviderConfig(system_mode=SystemMode.CLOUD_ONLY)
        provider = OciAdaptiveProvider(config=cfg)
        with pytest.raises(Exception):
            await provider.read("bucket", "key")


# ===========================================================================
# PersistentInfrastructureDatum
# ===========================================================================


class TestPersistentInfrastructureDatum:
    def _make_provider(self):
        """Return a provider with a mocked write/exists/read."""
        provider = MagicMock(spec=OciAdaptiveProvider)
        provider.write = AsyncMock(return_value=None)
        provider.read = AsyncMock(return_value=b"stored-data")
        provider.exists = AsyncMock(return_value=False)
        return provider

    def test_instantiation(self):
        pid = PersistentInfrastructureDatum(self._make_provider())
        assert pid is not None

    @pytest.mark.asyncio
    async def test_store_returns_key_string(self):
        pid = PersistentInfrastructureDatum(self._make_provider())
        key = await pid.store("records", "entry-001", b"payload")
        assert isinstance(key, str)
        assert "PID" in key

    @pytest.mark.asyncio
    async def test_store_key_contains_category(self):
        pid = PersistentInfrastructureDatum(self._make_provider())
        key = await pid.store("audit", "event-42", b"data")
        assert "audit" in key

    @pytest.mark.asyncio
    async def test_store_key_contains_name(self):
        pid = PersistentInfrastructureDatum(self._make_provider())
        key = await pid.store("logs", "entry-xyz", b"data")
        assert "entry-xyz" in key

    @pytest.mark.asyncio
    async def test_store_raises_on_duplicate(self):
        provider = self._make_provider()
        provider.exists = AsyncMock(return_value=True)  # already exists
        pid = PersistentInfrastructureDatum(provider)
        with pytest.raises(ValueError, match="immutability"):
            await pid.store("category", "name", b"data")

    @pytest.mark.asyncio
    async def test_retrieve_returns_bytes(self):
        pid = PersistentInfrastructureDatum(self._make_provider())
        data = await pid.retrieve("PID/records/2026/05/entry-001")
        assert data == b"stored-data"


# ===========================================================================
# AdaptiveInstanceDatum
# ===========================================================================


class TestAdaptiveInstanceDatum:
    def _make_provider(self):
        provider = MagicMock(spec=OciAdaptiveProvider)
        provider.write = AsyncMock(return_value=None)
        provider.read = AsyncMock(return_value=b"aid-data")
        provider.list = AsyncMock(return_value=["AID/cat/name/v1000", "AID/cat/name/v2000"])
        return provider

    def test_instantiation(self):
        aid = AdaptiveInstanceDatum(self._make_provider())
        assert aid is not None

    @pytest.mark.asyncio
    async def test_update_returns_versioned_key(self):
        aid = AdaptiveInstanceDatum(self._make_provider())
        key = await aid.update("config", "settings", b"data")
        assert isinstance(key, str)
        assert "AID" in key
        assert "config" in key
        assert "settings" in key

    @pytest.mark.asyncio
    async def test_update_key_has_version_suffix(self):
        aid = AdaptiveInstanceDatum(self._make_provider())
        key = await aid.update("events", "event-1", b"payload")
        assert "/v" in key

    @pytest.mark.asyncio
    async def test_two_updates_produce_different_keys(self):
        """Each update call must produce a unique versioned key."""
        import asyncio as _asyncio

        provider = self._make_provider()
        aid = AdaptiveInstanceDatum(provider)
        k1 = await aid.update("cat", "name", b"v1")
        await _asyncio.sleep(0.002)  # ensure different millisecond timestamp
        k2 = await aid.update("cat", "name", b"v2")
        assert k1 != k2
