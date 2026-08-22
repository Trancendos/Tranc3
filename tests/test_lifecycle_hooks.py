import pytest

from src.entities.lifecycle import LifecycleEmitter, LifecycleEvent


@pytest.mark.asyncio
async def test_lifecycle_emitter_exceptions():
    emitter = LifecycleEmitter("test_owner")

    # Test specific listener exception in async emit
    def crash_listener(ctx):
        raise ValueError("Intentional crash 1")

    # Test specific listener exception in sync emit
    def crash_listener_sync(ctx):
        raise ValueError("Intentional crash 2")

    # Test any listener exception in async emit
    def any_crash_listener(event, ctx):
        raise ValueError("Intentional crash 3")

    emitter.on_lifecycle(LifecycleEvent.START, crash_listener)
    emitter.on_lifecycle(LifecycleEvent.INIT, crash_listener_sync)
    emitter.on_any(any_crash_listener)

    # This should not crash, it should log errors and continue
    await emitter.emit_lifecycle(LifecycleEvent.START)
    emitter.emit_lifecycle_sync(LifecycleEvent.INIT)
