"""
Smoke Tests — The Spark + The Digital Grid.

Fast (<1 s total). Verify every critical subsystem can initialise and respond.
All tests produce structured log output via pytest caplog.
"""

from __future__ import annotations

import logging

import pytest

_log = logging.getLogger("tranc3.tests.smoke")


# ---------------------------------------------------------------------------
# The Spark — smoke
# ---------------------------------------------------------------------------


class TestSparkSmoke:
    def test_spark_tool_registry_initialises(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="tranc3.tests.smoke"):
            from src.mcp.tools import SparkToolRegistry

            reg = SparkToolRegistry()
            tool_count = len(reg.list_tools())
            _log.info("spark.smoke registry_init tools=%d", tool_count)
        assert tool_count > 0, "Spark registry must have built-in tools"
        assert any("health" in t["name"] for t in reg.list_tools())

    def test_spark_module_singleton_is_spark_tool_registry(self, caplog):
        with caplog.at_level(logging.DEBUG):
            from src.mcp.tools import SparkToolRegistry, registry

            _log.info("spark.smoke singleton_type=%s", type(registry).__name__)
        assert isinstance(registry, SparkToolRegistry)

    def test_spark_grid_constants_correct(self, caplog):
        from src.mcp.server import ENGINE_LABEL, SERVER_NAME
        from src.workflow.builder import GRID_ENGINE

        _log.info("spark.smoke server_name=%s engine=%s", SERVER_NAME, GRID_ENGINE)
        assert SERVER_NAME == "the-spark"
        assert GRID_ENGINE == "the-digital-grid"
        assert "Spark" in ENGINE_LABEL

    def test_spark_get_tool_returns_none_for_unknown(self, caplog):
        from src.mcp.tools import SparkToolRegistry

        reg = SparkToolRegistry()
        result = reg.get("__no_such_tool__")
        _log.info("spark.smoke unknown_tool result=%s", result)
        assert result is None

    def test_spark_list_tools_schema_valid(self, caplog):
        from src.mcp.tools import SparkToolRegistry

        reg = SparkToolRegistry()
        for tool in reg.list_tools():
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
        _log.info("spark.smoke all_tools_have_schema count=%d", len(reg.list_tools()))


# ---------------------------------------------------------------------------
# The Digital Grid — smoke
# ---------------------------------------------------------------------------


class TestDigitalGridSmoke:
    def test_workflow_builder_initialises(self, caplog):
        from src.workflow.builder import WorkflowBuilder

        b = WorkflowBuilder("smoke-test")
        _log.info("grid.smoke builder_init name=%s", b._name)
        assert b._name == "smoke-test"

    def test_workflow_executor_initialises(self, caplog):
        from src.workflow.executor import WorkflowExecutor

        ex = WorkflowExecutor()
        _log.info("grid.smoke executor_init executions=%d", len(ex.executions))
        assert isinstance(ex.executions, dict)

    def test_event_bus_subscribe_publish(self, caplog):
        import asyncio

        from src.workflow.executor import WorkflowEventBus

        bus = WorkflowEventBus()
        received = []
        bus.subscribe("smoke.event", lambda p: received.append(p))

        async def _run():
            await bus.publish("smoke.event", {"ping": True})

        asyncio.get_event_loop().run_until_complete(_run())
        _log.info("grid.smoke event_bus received=%d", len(received))
        assert received
        assert received[0]["data"]["ping"] is True

    @pytest.mark.asyncio
    async def test_minimal_workflow_executes(self, caplog, sample_workflow_definitions):
        from src.workflow.executor import WorkflowExecutor

        wf = sample_workflow_definitions["single_output"]
        ex = WorkflowExecutor()
        state = await ex.execute(wf, {"result": "smoke-ok"})
        _log.info(
            "grid.smoke min_workflow status=%s elapsed_ms=%.1f", state.status, state.elapsed_ms
        )
        assert state.status == "completed"
        assert state.elapsed_ms >= 0

    def test_node_type_spark_tool_registered(self, caplog):
        from src.workflow.nodes import NODE_REGISTRY, NodeType, SparkToolNode

        _log.info("grid.smoke node_registry size=%d", len(NODE_REGISTRY))
        assert NodeType.SPARK_TOOL in NODE_REGISTRY
        assert NODE_REGISTRY[NodeType.SPARK_TOOL] is SparkToolNode


# ---------------------------------------------------------------------------
# Error Catalog — smoke
# ---------------------------------------------------------------------------


class TestErrorCatalogSmoke:
    def test_error_catalog_imports(self, caplog):
        from src.errors.error_catalog import ErrorCode

        count = len(list(ErrorCode))
        _log.info("error_catalog.smoke codes=%d", count)
        assert count > 0

    def test_critical_error_domains_present(self, caplog):
        from src.errors.error_catalog import ErrorCode

        values = {e.value for e in list(ErrorCode)}
        domains = {v.split("-")[1] for v in values}
        _log.info("error_catalog.smoke domains=%s", sorted(domains))
        for required in ("AUTH", "RATE", "SEC", "MODEL", "SYS"):
            assert required in domains, f"Error domain {required} missing"

    def test_error_code_format(self, caplog):
        from src.errors.error_catalog import ErrorCode

        for code in list(ErrorCode):
            parts = code.value.split("-")
            assert len(parts) == 3, f"Bad format: {code.value}"
            assert parts[0] == "TRANC3"
            assert parts[2].isdigit()
        _log.info("error_catalog.smoke format_valid for all codes")


# ---------------------------------------------------------------------------
# NanoService — smoke
# ---------------------------------------------------------------------------


class TestNanoServiceSmoke:
    def test_nano_registry_initialises(self, caplog):
        from src.nanoservices.nano_registry import NanoServiceRegistry

        reg = NanoServiceRegistry()
        _log.info("nanoservice.smoke registry_type=%s", type(reg).__name__)
        assert reg is not None

    def test_nano_server_app_importable(self, caplog):
        from src.nanoservices.nano_server import nano_app

        _log.info("nanoservice.smoke app_title=%s", nano_app.title)
        assert nano_app is not None
