import pytest

from src.dependencies import ServiceContainer


def test_get_registered_singleton():
    """Test that get returns a previously registered singleton."""
    container = ServiceContainer()
    instance = {"some": "instance"}
    container.register_instance("my_service", instance)

    assert container.get("my_service") is instance


def test_get_unregistered_service_raises_key_error():
    """Test that get raises KeyError for an unregistered service."""
    container = ServiceContainer()

    with pytest.raises(KeyError, match="Service 'unregistered' not registered"):
        container.get("unregistered")


def test_get_invokes_factory_and_caches_instance():
    """Test that get invokes the factory, caches the result, and returns it."""
    container = ServiceContainer()

    factory_calls = 0

    def my_factory():
        nonlocal factory_calls
        factory_calls += 1
        return {"id": factory_calls}

    container.register_factory("lazy_service", my_factory, singleton=True)

    # First call should invoke the factory
    first_instance = container.get("lazy_service")
    assert first_instance == {"id": 1}
    assert factory_calls == 1

    # Second call should return the cached instance, not invoking factory again
    second_instance = container.get("lazy_service")
    assert second_instance is first_instance
    assert factory_calls == 1
