import pytest
import asyncio
from src.entities.lifecycle import LifecycleEmitter, LifecycleEvent, LifecycleContext

@pytest.mark.asyncio
async def test_emit_lifecycle_exceptions_logged(caplog):
    import logging
    caplog.set_level(logging.ERROR)

    emitter = LifecycleEmitter("test_emitter")

    def bad_listener(ctx):
        raise ValueError("Specific error")

    def bad_any_listener(event, ctx):
        raise TypeError("Any error")

    emitter.on_lifecycle(LifecycleEvent.START, bad_listener)
    emitter.on_any(bad_any_listener)

    await emitter.emit_lifecycle(LifecycleEvent.START)

    assert "Error in specific lifecycle listener for start" in caplog.text
    assert "Error in catch-all lifecycle listener for start" in caplog.text

def test_emit_lifecycle_sync_exceptions_logged(caplog):
    import logging
    caplog.set_level(logging.ERROR)

    emitter = LifecycleEmitter("test_emitter_sync")

    def bad_listener(ctx):
        raise ValueError("Specific sync error")

    def bad_any_listener(event, ctx):
        raise TypeError("Any sync error")

    emitter.on_lifecycle(LifecycleEvent.INIT, bad_listener)
    emitter.on_any(bad_any_listener)

    emitter.emit_lifecycle_sync(LifecycleEvent.INIT)

    assert "Error in specific sync lifecycle listener for init" in caplog.text
    assert "Error in catch-all sync lifecycle listener for init" in caplog.text
