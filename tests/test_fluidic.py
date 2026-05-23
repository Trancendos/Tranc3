# tests/test_fluidic.py — Tests for src/fluidic/reactive_state.py
"""Comprehensive tests for ReactiveState and StateStore."""

from __future__ import annotations

import pytest

from src.fluidic.reactive_state import ReactiveState, StateStore, state_store


# ── ReactiveState tests ────────────────────────────────────────────────────


class TestReactiveState:
    def test_initial_value(self):
        state = ReactiveState(initial=42, name="test")
        assert state.value == 42

    def test_name(self):
        state = ReactiveState(name="my-state")
        assert state._name == "my-state"

    def test_default_value_none(self):
        state = ReactiveState(name="empty")
        assert state.value is None

    @pytest.mark.asyncio
    async def test_set_value(self):
        state = ReactiveState(initial=0, name="counter")
        await state.set(10)
        assert state.value == 10

    @pytest.mark.asyncio
    async def test_set_dict(self):
        state = ReactiveState[dict](initial={}, name="config")
        await state.set({"key": "value"})
        assert state.value == {"key": "value"}

    @pytest.mark.asyncio
    async def test_update_dict(self):
        state = ReactiveState[dict](initial={"a": 1}, name="config")
        await state.update(a=2, b=3)
        assert state.value == {"a": 2, "b": 3}

    @pytest.mark.asyncio
    async def test_update_non_dict_noop(self):
        state = ReactiveState[int](initial=42, name="int-state")
        await state.update(x=1)  # Should be a no-op for non-dict
        assert state.value == 42

    @pytest.mark.asyncio
    async def test_subscribe_callback(self):
        state = ReactiveState(initial=0, name="test")
        received = []
        state.subscribe(lambda new, old: received.append((new, old)))
        await state.set(5)
        assert len(received) == 1
        assert received[0] == (5, 0)

    @pytest.mark.asyncio
    async def test_subscribe_async_callback(self):
        state = ReactiveState(initial=0, name="test")
        received = []

        async def on_change(new, old):
            received.append((new, old))

        state.subscribe(on_change)
        await state.set(5)
        assert len(received) == 1
        assert received[0] == (5, 0)

    @pytest.mark.asyncio
    async def test_no_notification_on_same_value(self):
        state = ReactiveState(initial=42, name="test")
        received = []
        state.subscribe(lambda new, old: received.append(new))
        await state.set(42)  # Same value
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        state = ReactiveState(initial=0, name="test")
        received = []
        callback = lambda new, old: received.append(new)  # noqa: E731
        state.subscribe(callback)
        state.unsubscribe(callback)
        await state.set(5)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_subscriber_error_handling(self):
        """Subscriber errors should not crash the notification loop."""
        state = ReactiveState(initial=0, name="test")
        received = []

        def bad_callback(new, old):
            raise RuntimeError("Subscriber error")

        def good_callback(new, old):
            received.append(new)

        state.subscribe(bad_callback)
        state.subscribe(good_callback)
        await state.set(5)
        # Good callback should still be called despite bad callback error
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_history(self):
        state = ReactiveState(initial=0, name="test")
        await state.set(1)
        await state.set(2)
        await state.set(3)
        assert state.history == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_history_max_length(self):
        state = ReactiveState(initial=0, name="test")
        state._max_history = 5
        for i in range(1, 10):
            await state.set(i)
        # History should be trimmed to last 5
        assert len(state.history) <= 5


# ── StateStore tests ────────────────────────────────────────────────────────


class TestStateStore:
    def test_create(self):
        store = StateStore()
        state = store.create("test", initial=42)
        assert state.value == 42
        assert state._name == "test"

    def test_get(self):
        store = StateStore()
        store.create("test", initial=42)
        state = store.get("test")
        assert state is not None
        assert state.value == 42

    def test_get_nonexistent(self):
        store = StateStore()
        assert store.get("missing") is None

    @pytest.mark.asyncio
    async def test_set(self):
        store = StateStore()
        store.create("test", initial=0)
        await store.set("test", 99)
        assert store.get("test").value == 99

    @pytest.mark.asyncio
    async def test_set_nonexistent(self):
        store = StateStore()
        await store.set("missing", 42)  # Should not raise

    def test_snapshot(self):
        store = StateStore()
        store.create("a", initial=1)
        store.create("b", initial=2)
        snap = store.snapshot()
        assert snap == {"a": 1, "b": 2}

    def test_module_singleton(self):
        """state_store module singleton should be a StateStore instance."""
        assert isinstance(state_store, StateStore)
