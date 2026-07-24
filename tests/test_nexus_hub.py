"""
Tests for src/nexus/hub.py — NexusHub (the in-process pub/sub actually wired
into api.py via src/nexus/routes.py, distinct from the workers/infinity-ws
WebSocket worker and from Dimensional/nexus/nexus_core.py's Nexus).

Covers the existing pub/sub + direct-send behavior, and the WS-hub fan-out
this session adds: NexusHub.publish() best-effort forwards each event to
workers/infinity-ws's POST /broadcast, so external WS clients subscribed
there see the same events section7/cryptex/the Digital Grid already publish
in-process. Previously nothing bridged the two — see docs/services/the-nexus
survey notes.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.nexus.hub import MessagePriority, MessageType, NexusHub


class TestNexusHubPubSub:
    def test_publish_delivers_to_subscriber_queue(self):
        hub = NexusHub()
        q = hub.subscribe_topic("audit.event")
        hub.publish("audit.event", {"foo": "bar"})
        msg = q.get_nowait()
        assert msg.topic == "audit.event"
        assert msg.payload == {"foo": "bar"}
        assert msg.type == MessageType.SERVICE_EVENT

    def test_unsubscribe_stops_delivery(self):
        hub = NexusHub()
        q = hub.subscribe_topic("audit.event")
        hub.unsubscribe_topic("audit.event", q)
        hub.publish("audit.event", {"foo": "bar"})
        assert q.empty()

    @pytest.mark.asyncio
    async def test_direct_send_requires_registered_recipient(self):
        hub = NexusHub()
        assert await hub.send("unregistered-service", {"x": 1}) is None
        q = hub.register_service("the-dutchy")
        msg = await hub.send("the-dutchy", {"x": 1})
        assert msg is not None
        assert q.get_nowait().payload == {"x": 1}


class TestNexusHubWsFanOut:
    """
    Regression coverage for NexusHub.publish() forwarding to
    workers/infinity-ws's /broadcast endpoint.
    """

    def test_publish_outside_event_loop_does_not_raise(self):
        # publish() is called from plain `def` methods elsewhere in the repo
        # (src/cryptex/threat_detector.py, src/section7/information_router.py)
        # that aren't guaranteed to run inside a running event loop — the WS
        # fan-out must degrade silently, not break the existing in-process path.
        hub = NexusHub()
        hub.publish("audit.event", {"foo": "bar"})  # no event loop running here

    @pytest.mark.asyncio
    async def test_publish_forwards_to_ws_hub_when_loop_is_running(self):
        hub = NexusHub()
        # raise_for_status is a *sync* method on a real httpx.Response — give
        # the mocked response a plain (non-async) one so nothing goes
        # unawaited when _post_broadcast calls it.
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=fake_response
        ) as mock_post:
            hub.publish("audit.event", {"foo": "bar"}, priority=MessagePriority.HIGH)
            # publish() schedules the forward via loop.create_task — let it run.
            await asyncio.sleep(0)

        assert mock_post.await_count == 1
        fake_response.raise_for_status.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["channel"] == "audit.event"
        assert kwargs["json"]["data"] == {"foo": "bar"}

    @pytest.mark.asyncio
    async def test_publish_does_not_propagate_http_error_status(self):
        hub = NexusHub()
        import httpx

        fake_response = MagicMock()
        fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403", request=MagicMock(), response=MagicMock(status_code=403)
        )
        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=fake_response
        ) as mock_post:
            hub.publish("audit.event", {"foo": "bar"})
            await asyncio.sleep(0)  # a rejected broadcast must not surface here

        assert mock_post.await_count == 1
        fake_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_ws_hub_unreachable_does_not_propagate(self):
        hub = NexusHub()
        with patch("httpx.AsyncClient.post", side_effect=OSError("connection refused")):
            hub.publish("audit.event", {"foo": "bar"})
            await asyncio.sleep(0)  # the swallowed exception must not surface here

    @pytest.mark.asyncio
    async def test_drops_forward_at_capacity_instead_of_piling_up(self):
        # A stuck/slow infinity-ws must not let a publish() burst accumulate
        # unbounded in-flight HTTP tasks. The capacity check+reservation
        # happens synchronously in _forward_to_ws_hub (before create_task),
        # so at-capacity publish() calls must never even schedule a task,
        # let alone make an HTTP call.
        from src.nexus import hub as hub_module

        hub = NexusHub()
        prior = hub_module._ws_forward_inflight
        hub_module._ws_forward_inflight = hub_module._WS_FORWARD_CONCURRENCY
        try:
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                hub.publish("audit.event", {"foo": "bar"})
                await asyncio.sleep(0)
            mock_post.assert_not_called()
            # The dropped call must not have incremented the counter either.
            assert hub_module._ws_forward_inflight == hub_module._WS_FORWARD_CONCURRENCY
        finally:
            hub_module._ws_forward_inflight = prior
