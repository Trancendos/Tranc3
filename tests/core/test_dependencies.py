import pytest
from src.dependencies import ServiceContainer

def test_list_services_empty():
    """Test list_services returns empty dict for empty container"""
    container = ServiceContainer()
    assert container.list_services() == {}

def test_list_services_with_factories_and_singletons():
    """Test list_services correctly identifies lazy, initialized and direct services"""
    container = ServiceContainer()

    # Register factory (lazy)
    container.register_factory("db", lambda: "db_instance", singleton=True)

    # Register instance (direct)
    container.register_instance("config", "config_instance")

    services = container.list_services()

    assert "db" in services
    assert services["db"] == "lazy"

    assert "config" in services
    assert services["config"] == "direct"

    # Resolve the factory, it should become initialized
    container.get("db")

    services = container.list_services()
    assert services["db"] == "initialized"

def test_list_services_return_type():
    """Test list_services returns a dictionary mapping strings to strings"""
    container = ServiceContainer()
    container.register_instance("test", "value")
    result = container.list_services()
    assert isinstance(result, dict)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in result.items())

def test_list_services_sorted_keys():
    """Test if list_services or keys of returned dict are in expected order (if any)"""
    container = ServiceContainer()
    container.register_factory("z_service", lambda: 1)
    container.register_factory("a_service", lambda: 2)
    container.register_instance("m_service", 3)

    services = container.list_services()
    assert len(services) == 3
    assert set(services.keys()) == {"z_service", "a_service", "m_service"}
