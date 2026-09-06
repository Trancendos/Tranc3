"""Tests for src/dependencies.py (ServiceContainer and configure_services).

Combined from five PRs that each created this file from scratch to cover a
different part of the container: #907 (get), #900 (has), #926 (register_instance
and register_factory interaction), #882 (reset) and #889 (configure_services).

A sixth, #881, is deliberately not carried over. It removed the singleton
parameter from register_factory, which is a breaking signature change:
tests/core/test_dependencies.py (merged as #909) and #907's own
test_get_invokes_factory_and_caches_instance both call it with singleton=True.
Its two tests duplicate coverage provided here.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.dependencies import ServiceContainer, configure_services, container

# ── get (#907) ───────────────────────────────────────────────────────────────


def test_get_registered_singleton():
    """get returns a previously registered singleton."""
    sc = ServiceContainer()
    instance = {"some": "instance"}
    sc.register_instance("my_service", instance)

    assert sc.get("my_service") is instance


def test_get_unregistered_service_raises_key_error():
    """get raises KeyError for an unregistered service."""
    sc = ServiceContainer()

    with pytest.raises(KeyError, match="Service 'unregistered' not registered"):
        sc.get("unregistered")


def test_get_invokes_factory_and_caches_instance():
    """get invokes the factory once, caches the result, and returns it."""
    sc = ServiceContainer()

    factory_calls = 0

    def my_factory():
        nonlocal factory_calls
        factory_calls += 1
        return {"id": factory_calls}

    sc.register_factory("lazy_service", my_factory, singleton=True)

    first_instance = sc.get("lazy_service")
    assert first_instance == {"id": 1}
    assert factory_calls == 1

    second_instance = sc.get("lazy_service")
    assert second_instance is first_instance
    assert factory_calls == 1


# ── has (#900) ───────────────────────────────────────────────────────────────


def test_service_container_has():
    """has identifies services registered by either route."""
    sc = ServiceContainer()

    assert sc.has("unregistered_service") is False

    sc.register_factory("factory_service", lambda: "factory_instance")
    assert sc.has("factory_service") is True

    sc.register_instance("instance_service", "instance_value")
    assert sc.has("instance_service") is True


def test_service_container_has_internal_state_direct():
    """has reads both internal maps, not just the public registration path."""
    sc = ServiceContainer()

    sc._factories["direct_factory"] = lambda: 1
    assert sc.has("direct_factory") is True

    sc._singletons["direct_singleton"] = "value"
    assert sc.has("direct_singleton") is True

    assert sc.has("missing_service") is False


# ── register_instance / register_factory interaction (#926) ──────────────────


def test_register_instance_supersedes_a_factory_of_the_same_name():
    sc = ServiceContainer()

    sc.register_factory("test_service", lambda: "factory_instance")
    assert "test_service" in sc._factories

    sc.register_instance("test_service", "direct_instance")

    assert sc._singletons["test_service"] == "direct_instance"
    assert "test_service" not in sc._factories
    assert sc.get("test_service") == "direct_instance"


def test_register_factory_non_singleton_clears_an_existing_instance():
    sc = ServiceContainer()

    sc.register_instance("test_service", "direct_instance")
    assert "test_service" in sc._singletons

    sc.register_factory("test_service", lambda: "factory_instance", singleton=False)

    assert "test_service" not in sc._singletons
    assert "test_service" in sc._factories


# ── reset (#882) ─────────────────────────────────────────────────────────────


def test_service_container_reset():
    """reset clears registrations, singletons, and the initialized flag."""
    sc = ServiceContainer()
    sc.register_factory("test_svc", lambda: "test_instance")
    sc.register_instance("test_direct", "direct_instance")
    sc._initialized = True

    assert sc.get("test_svc") == "test_instance"
    assert sc.has("test_svc")
    assert sc.has("test_direct")
    assert "test_svc" in sc._singletons
    assert "test_svc" in sc._factories
    assert "test_direct" in sc._singletons

    sc.reset()

    assert len(sc._singletons) == 0
    assert len(sc._factories) == 0
    assert not sc._initialized
    assert not sc.has("test_svc")
    assert not sc.has("test_direct")


# ── configure_services (#889) ────────────────────────────────────────────────
#
# These exercise the module-global container rather than a local instance,
# because configure_services() registers onto that global. The fixture restores
# it afterwards as well as before, which #889 did not do — without the teardown
# these tests leave the global populated for whatever runs next.


@pytest.fixture
def clean_global_container():
    container.reset()
    yield container
    container.reset()


def test_configure_services_registers_factories(clean_global_container):
    assert container._initialized is False

    mock_config = MagicMock()
    mock_config.REDIS_URL = "redis://localhost:6379"
    mock_config.DATABASE_URL = "sqlite:///:memory:"

    with patch("src.core.config.settings", mock_config):
        configure_services()

    expected_services = [
        "redis",
        "db",
        "feature_flags",
        "vector_store",
        "personality",
        "consciousness",
        "evolution",
        "quantum",
    ]
    for service in expected_services:
        assert container.has(service)

    assert container._initialized is True


def test_configure_services_optional_imports_degrade_to_none(clean_global_container):
    mock_config = MagicMock()
    mock_config.REDIS_URL = "redis://localhost:6379"
    mock_config.DATABASE_URL = "sqlite:///:memory:"

    with patch.dict(
        "sys.modules",
        {
            "src.personality.matrix": None,
            "src.bio_neural.consciousness_engine": None,
            "src.evolution.self_improving_core": None,
            "src.quantum.quantum_core": None,
        },
    ):
        with patch("src.core.config.settings", mock_config):
            configure_services()

        assert container.get("personality") is None
        assert container.get("consciousness") is None
        assert container.get("evolution") is None
        assert container.get("quantum") is None
