import pytest
from src.main_enhanced import TRANC3Enhanced


@pytest.mark.asyncio
async def test_execute_workflow_no_executor():
    t3e = TRANC3Enhanced()
    result = await t3e.execute_workflow({"test": "definition"}, {"test": "input"})
    assert result == {"error": "Workflow executor not available"}


class MockWorkflowState:
    def __init__(self, execution_id, status, node_outputs, error=None):
        self.execution_id = execution_id
        self.status = status
        self.node_outputs = node_outputs
        self.error = error


class MockWorkflowExecutor:
    async def execute(self, workflow, inputs):
        self.last_workflow = workflow
        self.last_inputs = inputs
        return MockWorkflowState("exec-123", "completed", {"node1": "output1"})


@pytest.mark.asyncio
async def test_execute_workflow_success():
    t3e = TRANC3Enhanced()
    mock_executor = MockWorkflowExecutor()
    t3e._subsystems["workflow_executor"] = mock_executor

    workflow_def = {
        "name": "test_workflow",
        "steps": [{"step_id": "step1", "name": "Step 1", "action": "test_action"}],
    }
    inputs = {"test": "input"}

    result = await t3e.execute_workflow(workflow_def, inputs)

    assert result == {
        "execution_id": "exec-123",
        "status": "completed",
        "outputs": {"node1": "output1"},
        "error": None,
    }

    # Check inputs were passed correctly
    assert mock_executor.last_inputs == inputs
    assert mock_executor.last_workflow.name == "test_workflow"


@pytest.mark.asyncio
async def test_execute_workflow_no_inputs():
    t3e = TRANC3Enhanced()
    mock_executor = MockWorkflowExecutor()
    t3e._subsystems["workflow_executor"] = mock_executor

    workflow_def = {
        "name": "test_workflow",
        "steps": [{"step_id": "step1", "name": "Step 1", "action": "test_action"}],
    }

    result = await t3e.execute_workflow(workflow_def)

    assert result == {
        "execution_id": "exec-123",
        "status": "completed",
        "outputs": {"node1": "output1"},
        "error": None,
    }

    # Check default inputs were used
    assert mock_executor.last_inputs == {}
