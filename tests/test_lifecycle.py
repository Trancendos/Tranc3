import asyncio
import logging

from src.entities.lifecycle import LifecycleEmitter, LifecycleEvent


def test_emit_lifecycle_exceptions_logged(caplog):
    """Test that exceptions in listeners are logged and do not crash the emitter."""
    emitter = LifecycleEmitter("test_entity")

    def failing_listener(ctx):
        raise ValueError("Intentional crash in specific listener")

    async def failing_async_listener(ctx):
        raise ValueError("Intentional crash in async listener")

    def failing_any_listener(event, ctx):
        raise ValueError("Intentional crash in any listener")

    emitter.on_lifecycle(LifecycleEvent.START, failing_listener)
    emitter.on_lifecycle(LifecycleEvent.START, failing_async_listener)
    emitter.on_any(failing_any_listener)

    with caplog.at_level(logging.ERROR):
        # Async emit
        asyncio.run(emitter.emit_lifecycle(LifecycleEvent.START))

        # Sync emit
        emitter.emit_lifecycle_sync(LifecycleEvent.START)

    # Check logs
    assert "Intentional crash in specific listener" in caplog.text
    assert "Intentional crash in async listener" in caplog.text
    assert "Intentional crash in any listener" in caplog.text
