from src.dependencies import ServiceContainer


def test_register_instance():
    container = ServiceContainer()

    # First, register a factory
    container.register_factory("test_service", lambda: "factory_instance")
    assert "test_service" in container._factories

    # Now, register an instance with the same name
    container.register_instance("test_service", "direct_instance")

    # Verify that the instance was added to singletons
    assert container._singletons["test_service"] == "direct_instance"

    # Verify that the factory was removed
    assert "test_service" not in container._factories

    # Verify that get() returns the instance
    assert container.get("test_service") == "direct_instance"


def test_register_factory_removes_singleton():
    container = ServiceContainer()

    # First, register an instance
    container.register_instance("test_service", "direct_instance")
    assert "test_service" in container._singletons

    # Now, register a factory with singleton=False
    container.register_factory("test_service", lambda: "factory_instance", singleton=False)

    # Verify that the singleton was removed
    assert "test_service" not in container._singletons

    # Verify that the factory was added
    assert "test_service" in container._factories
