"""Tests for the dependency injection container."""

from src.dependencies import ServiceContainer


def test_service_container_has():
    """Verify ServiceContainer.has correctly identifies registered services."""
    sc = ServiceContainer()

    # Test un-registered service
    assert sc.has("unregistered_service") is False

    # Test registered factory
    sc.register_factory("factory_service", lambda: "factory_instance")
    assert sc.has("factory_service") is True

    # Test registered instance
    sc.register_instance("instance_service", "instance_value")
    assert sc.has("instance_service") is True


def test_service_container_has_internal_state_direct():
    """Verify ServiceContainer.has by setting internal state directly (fallback validation)."""
    sc = ServiceContainer()

    sc._factories["direct_factory"] = lambda: 1
    assert sc.has("direct_factory") is True

    sc._singletons["direct_singleton"] = "value"
    assert sc.has("direct_singleton") is True

    assert sc.has("missing_service") is False
