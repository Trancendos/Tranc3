import pytest
from src.dependencies import ServiceContainer

def test_register_factory_clears_singleton():
    """Test that register_factory clears any existing singleton instance."""
    container = ServiceContainer()

    # 1. Register a pre-built instance
    container.register_instance("my_service", "old_instance")
    assert container.get("my_service") == "old_instance"

    # 2. Register a new factory
    call_count = 0
    def mock_factory():
        nonlocal call_count
        call_count += 1
        return f"instance_{call_count}"

    container.register_factory("my_service", mock_factory)

    # 3. Verify the old instance was cleared and the factory is used
    assert container.get("my_service") == "instance_1"

    # 4. Verify it acts as a singleton after the first get
    assert container.get("my_service") == "instance_1"
    assert call_count == 1

def test_get_unregistered_service_raises_keyerror():
    """Test that get() raises KeyError for unregistered services."""
    container = ServiceContainer()
    with pytest.raises(KeyError, match="Service 'missing' not registered"):
        container.get("missing")
