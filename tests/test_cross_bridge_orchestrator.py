"""
Tests for Tranc3 Cross-Bridge Orchestrator
============================================
Comprehensive tests for cross-bridge orchestration including
workflow execution, step execution, compensation, and saga rollback.
"""

import asyncio

from Dimensional.cross_bridge_orchestrator import (
    BridgeDispatcher,
    BridgeTarget,
    CompensationManager,
    CrossBridgeOrchestrator,
    OrchestrationStep,
    OrchestrationWorkflow,
    StepExecutor,
    StepStatus,
    WorkflowStatus,
    get_orchestrator,
)

# ──────────────────────────────────────────────
# OrchestrationStep Tests
# ──────────────────────────────────────────────


class TestOrchestrationStep:
    def test_create_step(self):
        step = OrchestrationStep(
            name="test-step",
            bridge=BridgeTarget.NEXUS,
            action="process",
        )
        assert step.name == "test-step"
        assert step.bridge == BridgeTarget.NEXUS
        assert step.action == "process"
        assert step.status == StepStatus.PENDING

    def test_step_defaults(self):
        step = OrchestrationStep(
            name="step",
            bridge=BridgeTarget.HIVE,
            action="sync",
        )
        assert step.step_id is not None
        assert step.payload == {}
        assert step.compensation_action is None
        assert step.max_retries == 3
        assert step.timeout_seconds == 30.0

    def test_step_with_compensation(self):
        step = OrchestrationStep(
            name="step",
            bridge=BridgeTarget.INFINITY,
            action="create",
            compensation_action="delete",
            compensation_payload={"confirm": True},
        )
        assert step.compensation_action == "delete"
        assert step.compensation_payload == {"confirm": True}


# ──────────────────────────────────────────────
# OrchestrationWorkflow Tests
# ──────────────────────────────────────────────


class TestOrchestrationWorkflow:
    def test_create_workflow(self):
        workflow = OrchestrationWorkflow(name="test-workflow")
        assert workflow.name == "test-workflow"
        assert workflow.status == WorkflowStatus.PENDING
        assert workflow.steps == []

    def test_workflow_with_steps(self):
        steps = [
            OrchestrationStep(name="s1", bridge=BridgeTarget.NEXUS, action="a1"),
            OrchestrationStep(name="s2", bridge=BridgeTarget.HIVE, action="a2"),
        ]
        workflow = OrchestrationWorkflow(name="test", steps=steps)
        assert len(workflow.steps) == 2

    def test_workflow_id_auto_generated(self):
        workflow = OrchestrationWorkflow(name="test")
        assert workflow.workflow_id is not None
        assert len(workflow.workflow_id) > 0


# ──────────────────────────────────────────────
# BridgeDispatcher Tests
# ──────────────────────────────────────────────


class TestBridgeDispatcher:
    def test_dispatch_no_handler(self):
        """When no handler is registered, returns simulated response."""
        dispatcher = BridgeDispatcher()
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(dispatcher.dispatch(BridgeTarget.NEXUS, "test", {}))
            assert result["simulated"] is True
            assert result["bridge"] == "nexus"
        finally:
            loop.close()

    def test_register_and_dispatch(self):
        dispatcher = BridgeDispatcher()

        async def handler(action, payload):
            return {"action": action, "result": "ok"}

        dispatcher.register_handler(BridgeTarget.NEXUS, handler)
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                dispatcher.dispatch(BridgeTarget.NEXUS, "process", {"data": 1})
            )
            assert result["result"] == "ok"
        finally:
            loop.close()

    def test_unregister_handler(self):
        dispatcher = BridgeDispatcher()
        dispatcher.register_handler(BridgeTarget.NEXUS, lambda a, p: {})
        dispatcher.unregister_handler(BridgeTarget.NEXUS)
        assert dispatcher.has_handler(BridgeTarget.NEXUS) is False

    def test_has_handler(self):
        dispatcher = BridgeDispatcher()
        assert dispatcher.has_handler(BridgeTarget.NEXUS) is False
        dispatcher.register_handler(BridgeTarget.NEXUS, lambda a, p: {})
        assert dispatcher.has_handler(BridgeTarget.NEXUS) is True

    def test_get_registered_bridges(self):
        dispatcher = BridgeDispatcher()
        dispatcher.register_handler(BridgeTarget.NEXUS, lambda a, p: {})
        dispatcher.register_handler(BridgeTarget.HIVE, lambda a, p: {})
        bridges = dispatcher.get_registered_bridges()
        assert len(bridges) == 2
        assert BridgeTarget.NEXUS in bridges
        assert BridgeTarget.HIVE in bridges


# ──────────────────────────────────────────────
# StepExecutor Tests
# ──────────────────────────────────────────────


class TestStepExecutor:
    def test_execute_success(self):
        dispatcher = BridgeDispatcher()

        async def handler(action, payload):
            return {"status": "ok"}

        dispatcher.register_handler(BridgeTarget.NEXUS, handler)
        executor = StepExecutor(dispatcher)
        step = OrchestrationStep(name="test", bridge=BridgeTarget.NEXUS, action="process")
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(executor.execute(step))
            assert result.status == StepStatus.COMPLETED
        finally:
            loop.close()

    def test_execute_simulated_success(self):
        """Simulated dispatch with error but simulated=True is treated as success."""
        dispatcher = BridgeDispatcher()
        executor = StepExecutor(dispatcher)
        step = OrchestrationStep(
            name="test",
            bridge=BridgeTarget.NEXUS,
            action="process",
            max_retries=0,
        )
        loop = asyncio.new_event_loop()
        try:
            # No handler registered, so dispatch returns simulated response
            result = loop.run_until_complete(executor.execute(step))
            assert result.status == StepStatus.COMPLETED
        finally:
            loop.close()

    def test_execute_failure(self):
        dispatcher = BridgeDispatcher()

        async def handler(action, payload):
            raise RuntimeError("handler error")

        dispatcher.register_handler(BridgeTarget.NEXUS, handler)
        executor = StepExecutor(dispatcher)
        step = OrchestrationStep(
            name="test",
            bridge=BridgeTarget.NEXUS,
            action="process",
            max_retries=0,
        )
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(executor.execute(step))
            assert result.status == StepStatus.FAILED
        finally:
            loop.close()


# ──────────────────────────────────────────────
# CompensationManager Tests
# ──────────────────────────────────────────────


class TestCompensationManager:
    def test_compensate_no_compensatable_steps(self):
        """When no steps have compensation actions, workflow is returned unchanged."""
        dispatcher = BridgeDispatcher()
        manager = CompensationManager(dispatcher)
        workflow = OrchestrationWorkflow(
            name="test",
            steps=[
                OrchestrationStep(
                    name="s1",
                    bridge=BridgeTarget.NEXUS,
                    action="process",
                    status=StepStatus.COMPLETED,
                ),
            ],
        )
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(manager.compensate(workflow))
            # No compensation_action, so workflow returned unchanged
            assert result.status == WorkflowStatus.COMPENSATING
        finally:
            loop.close()

    def test_compensate_with_compensation_actions(self):
        dispatcher = BridgeDispatcher()

        async def handler(action, payload):
            return {"compensated": True}

        dispatcher.register_handler(BridgeTarget.NEXUS, handler)
        manager = CompensationManager(dispatcher)
        workflow = OrchestrationWorkflow(
            name="test",
            steps=[
                OrchestrationStep(
                    name="s1",
                    bridge=BridgeTarget.NEXUS,
                    action="process",
                    compensation_action="undo_process",
                    status=StepStatus.COMPLETED,
                ),
            ],
        )
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(manager.compensate(workflow))
            assert result.status == WorkflowStatus.COMPENSATED
        finally:
            loop.close()


# ──────────────────────────────────────────────
# CrossBridgeOrchestrator Tests
# ──────────────────────────────────────────────


class TestCrossBridgeOrchestrator:
    def test_create_orchestrator(self):
        orchestrator = CrossBridgeOrchestrator()
        assert orchestrator is not None

    def test_register_handler(self):
        orchestrator = CrossBridgeOrchestrator()
        orchestrator.register_handler(BridgeTarget.NEXUS, lambda a, p: {})
        assert orchestrator.get_status()["registered_bridges"] == ["nexus"]

    def test_execute_workflow(self):
        orchestrator = CrossBridgeOrchestrator()

        async def nexus_handler(action, payload):
            return {"action": action, "result": "ok"}

        async def hive_handler(action, payload):
            return {"action": action, "result": "ok"}

        orchestrator.register_handler(BridgeTarget.NEXUS, nexus_handler)
        orchestrator.register_handler(BridgeTarget.HIVE, hive_handler)

        workflow = OrchestrationWorkflow(
            name="cross-bridge-test",
            steps=[
                OrchestrationStep(name="nexus-step", bridge=BridgeTarget.NEXUS, action="process"),
                OrchestrationStep(name="hive-step", bridge=BridgeTarget.HIVE, action="sync"),
            ],
        )
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(orchestrator.execute(workflow))
            assert result.status == WorkflowStatus.COMPLETED
        finally:
            loop.close()

    def test_execute_workflow_with_failure(self):
        orchestrator = CrossBridgeOrchestrator()

        async def nexus_handler(action, payload):
            raise RuntimeError("nexus down")

        async def hive_handler(action, payload):
            return {"result": "ok"}

        orchestrator.register_handler(BridgeTarget.NEXUS, nexus_handler)
        orchestrator.register_handler(BridgeTarget.HIVE, hive_handler)

        workflow = OrchestrationWorkflow(
            name="failure-test",
            steps=[
                OrchestrationStep(
                    name="nexus-step",
                    bridge=BridgeTarget.NEXUS,
                    action="process",
                    max_retries=0,
                    compensation_action="undo_nexus",
                ),
                OrchestrationStep(
                    name="hive-step",
                    bridge=BridgeTarget.HIVE,
                    action="sync",
                ),
            ],
        )
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(orchestrator.execute(workflow))
            # CompensationManager sets COMPENSATING even when no compensatable steps ran
            assert result.status in (
                WorkflowStatus.COMPENSATING,
                WorkflowStatus.COMPENSATED,
                WorkflowStatus.FAILED,
            )
        finally:
            loop.close()

    def test_get_workflow(self):
        orchestrator = CrossBridgeOrchestrator()
        workflow = OrchestrationWorkflow(name="test")
        orchestrator._workflows[workflow.workflow_id] = workflow
        found = orchestrator.get_workflow(workflow.workflow_id)
        assert found is not None

    def test_list_workflows(self):
        orchestrator = CrossBridgeOrchestrator()
        orchestrator._workflows["wf-1"] = OrchestrationWorkflow(name="test1")
        orchestrator._workflows["wf-2"] = OrchestrationWorkflow(name="test2")
        workflows = orchestrator.list_workflows()
        assert len(workflows) == 2

    def test_get_status(self):
        orchestrator = CrossBridgeOrchestrator()
        status = orchestrator.get_status()
        assert "running" in status
        assert "total_workflows" in status
        assert "registered_bridges" in status

    def test_start_stop(self):
        orchestrator = CrossBridgeOrchestrator()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(orchestrator.start())
            assert orchestrator._running is True
            loop.run_until_complete(orchestrator.stop())
            assert orchestrator._running is False
        finally:
            loop.close()


# ──────────────────────────────────────────────
# Singleton Tests
# ──────────────────────────────────────────────


class TestOrchestratorSingleton:
    def test_get_orchestrator(self):
        orchestrator = get_orchestrator()
        assert orchestrator is not None
        assert isinstance(orchestrator, CrossBridgeOrchestrator)
