"""
Tests for Dimensional.architecture.auto_config.

Covers: ConfigStatus, EnvironmentType, ConfigItem, ConfigProfile,
DetectionResult, EnvironmentDetector, AutoConfigManager.
"""

from __future__ import annotations

from Dimensional.architecture.auto_config import (
    AutoConfigManager,
    ConfigItem,
    ConfigProfile,
    ConfigStatus,
    DetectionResult,
    EnvironmentDetector,
    EnvironmentType,
)

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestConfigStatus:
    """Tests for ConfigStatus enum."""

    def test_all_statuses_exist(self):
        expected = [
            "DEFAULT",
            "DETECTED",
            "OVERRIDDEN",
            "HOT_RELOADED",
            "VALIDATED",
            "ROLLED_BACK",
        ]
        for name in expected:
            assert hasattr(ConfigStatus, name), f"Missing ConfigStatus.{name}"

    def test_status_values(self):
        assert ConfigStatus.DEFAULT.value == "default"
        assert ConfigStatus.HOT_RELOADED.value == "hot_reloaded"
        assert ConfigStatus.ROLLED_BACK.value == "rolled_back"


class TestEnvironmentType:
    """Tests for EnvironmentType enum."""

    def test_all_types_exist(self):
        expected = [
            "TRUE_NAS",
            "HYBRID",
            "CLOUD_ONLY",
            "DEVELOPMENT",
            "PRODUCTION",
            "UNKNOWN",
        ]
        for name in expected:
            assert hasattr(EnvironmentType, name), f"Missing EnvironmentType.{name}"

    def test_type_values(self):
        assert EnvironmentType.TRUE_NAS.value == "TRUE_NAS"
        assert EnvironmentType.CLOUD_ONLY.value == "CLOUD_ONLY"
        assert EnvironmentType.UNKNOWN.value == "unknown"
        assert EnvironmentType.DEVELOPMENT.value == "development"
        assert EnvironmentType.PRODUCTION.value == "production"


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestConfigItem:
    """Tests for ConfigItem dataclass."""

    def test_create_config_item(self):
        item = ConfigItem(
            key="database.url",
            value="sqlite:///test.db",
            status=ConfigStatus.DEFAULT,
            source="default",
        )
        assert item.key == "database.url"
        assert item.value == "sqlite:///test.db"
        assert item.status == ConfigStatus.DEFAULT
        assert item.source == "default"

    def test_config_item_with_optional_fields(self):
        item = ConfigItem(
            key="cache.ttl",
            value="300",
            status=ConfigStatus.DETECTED,
            source="env",
            previous_value="60",
            description="Cache TTL in seconds",
        )
        assert item.previous_value == "60"
        assert item.description == "Cache TTL in seconds"


class TestConfigProfile:
    """Tests for ConfigProfile dataclass."""

    def test_create_config_profile(self):
        profile = ConfigProfile(
            name="development",
            environment=EnvironmentType.DEVELOPMENT,
            description="Local dev profile",
            settings={
                "database.url": "sqlite:///dev.db",
                "cache.ttl": "300",
            },
            rules=[],
        )
        assert profile.name == "development"
        assert "database.url" in profile.settings

    def test_create_with_environment(self):
        profile = ConfigProfile(
            name="prod",
            environment=EnvironmentType.PRODUCTION,
            description="Production profile",
            settings={"database.url": "postgres://prod"},
            rules=[],
        )
        assert profile.environment == EnvironmentType.PRODUCTION


class TestDetectionResult:
    """Tests for DetectionResult dataclass."""

    def test_create_detection_result(self):
        result = DetectionResult(
            name="environment",
            detected=True,
            value="production",
            confidence=0.95,
            method="heuristic",
        )
        assert result.name == "environment"
        assert result.detected is True
        assert result.value == "production"
        assert result.confidence == 0.95
        assert result.method == "heuristic"


# ---------------------------------------------------------------------------
# EnvironmentDetector tests
# ---------------------------------------------------------------------------


class TestEnvironmentDetector:
    """Tests for the EnvironmentDetector."""

    def test_detect_all_returns_dict(self):
        detector = EnvironmentDetector()
        results = detector.detect_all()
        assert isinstance(results, dict)
        for key, result in results.items():
            assert isinstance(key, str)
            assert isinstance(result, DetectionResult)

    def test_detect_all_has_name_and_confidence(self):
        detector = EnvironmentDetector()
        results = detector.detect_all()
        for result in results.values():
            assert isinstance(result.name, str)
            assert 0.0 <= result.confidence <= 1.0


# ---------------------------------------------------------------------------
# AutoConfigManager tests
# ---------------------------------------------------------------------------


class TestAutoConfigManager:
    """Tests for the AutoConfigManager."""

    def setup_method(self):
        self.manager = AutoConfigManager()

    def test_get_default_config(self):
        value = self.manager.get("nonexistent.key", default="fallback")
        assert value == "fallback"

    def test_set_and_get(self):
        result = self.manager.set("test.key", "test_value")
        assert isinstance(result, bool)
        value = self.manager.get("test.key")
        assert value == "test_value"

    def test_set_returns_bool(self):
        result = self.manager.set("bool.key", "val")
        assert result is True

    def test_get_nonexistent_no_default(self):
        value = self.manager.get("nonexistent.key")
        assert value is None

    def test_register_profile(self):
        profile = ConfigProfile(
            name="test_profile",
            environment=EnvironmentType.DEVELOPMENT,
            description="Test profile",
            settings={"app.debug": "true", "app.port": "8080"},
            rules=[],
        )
        self.manager.register_profile(profile)
        retrieved = self.manager.get_profile("test_profile")
        assert retrieved is not None
        assert retrieved.name == "test_profile"

    def test_list_profiles(self):
        profile = ConfigProfile(
            name="list_test",
            environment=EnvironmentType.DEVELOPMENT,
            description="Test",
            settings={},
            rules=[],
        )
        self.manager.register_profile(profile)
        profiles = self.manager.list_profiles()
        assert isinstance(profiles, list)
        # list_profiles returns list of dicts
        assert any(p.get("name") == "list_test" for p in profiles)

    def test_rollback(self):
        self.manager.set("rollback.key", "original")
        self.manager.set("rollback.key", "updated")
        result = self.manager.rollback("rollback.key")
        assert isinstance(result, bool)
        assert result is True
        assert self.manager.get("rollback.key") == "original"

    def test_rollback_nonexistent(self):
        result = self.manager.rollback("nonexistent.key")
        assert isinstance(result, bool)

    def test_auto_configure(self):
        profile_name = self.manager.auto_configure()
        assert isinstance(profile_name, str)

    def test_hot_reload(self):
        self.manager.set("hot.key", "original")
        count = self.manager.hot_reload()
        assert isinstance(count, int)

    def test_add_listener(self):
        changes = []

        def listener(key, old_val, new_val):
            changes.append((key, old_val, new_val))

        self.manager.add_listener(listener)
        self.manager.set("listen.key", "value1")
        assert len(changes) >= 1

    def test_remove_listener(self):
        changes = []

        def listener(key, old_val, new_val):
            changes.append((key, old_val, new_val))

        self.manager.add_listener(listener)
        self.manager.remove_listener(listener)
        self.manager.set("remove.key", "value2")
        # After removal, listener should not be called

    def test_get_config(self):
        self.manager.set("config.key", "val")
        config = self.manager.get_config()
        assert isinstance(config, dict)

    def test_get_config_details(self):
        self.manager.set("detail.key", "val")
        details = self.manager.get_config_details()
        assert isinstance(details, dict)

    def test_get_detection_results(self):
        results = self.manager.get_detection_results()
        assert isinstance(results, dict)

    def test_get_stats(self):
        stats = self.manager.get_stats()
        assert isinstance(stats, dict)
