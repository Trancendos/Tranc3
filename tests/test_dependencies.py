from src.dependencies import ServiceContainer


def test_service_container_reset():
    """Test that reset() clears all registrations, singletons, and the initialized flag."""
    test_container = ServiceContainer()
    test_container.register_factory("test_svc", lambda: "test_instance")
    test_container.register_instance("test_direct", "direct_instance")

    test_container._initialized = True

    # Resolve to populate singleton
    instance = test_container.get("test_svc")
    assert instance == "test_instance"

    assert test_container.has("test_svc")
    assert test_container.has("test_direct")

    assert "test_svc" in test_container._singletons
    assert "test_svc" in test_container._factories
    assert "test_direct" in test_container._singletons

    test_container.reset()

    assert len(test_container._singletons) == 0
    assert len(test_container._factories) == 0
    assert not test_container._initialized
    assert not test_container.has("test_svc")
    assert not test_container.has("test_direct")
