import pytest
from unittest.mock import AsyncMock, MagicMock

from src.main_enhanced import TRANC3Enhanced

@pytest.mark.asyncio
async def test_call_mcp_tool_missing_registry():
    app = TRANC3Enhanced()
    app._subsystems = {}
    result = await app.call_mcp_tool("some_tool")
    assert result == {"error": "MCP registry not available"}

@pytest.mark.asyncio
async def test_call_mcp_tool_missing_tool():
    app = TRANC3Enhanced()
    mock_registry = MagicMock()
    mock_registry.get.return_value = None
    app._subsystems = {"mcp_registry": mock_registry}

    result = await app.call_mcp_tool("missing_tool")

    assert result == {"error": "Tool 'missing_tool' not found"}
    mock_registry.get.assert_called_once_with("missing_tool")

@pytest.mark.asyncio
async def test_call_mcp_tool_success():
    app = TRANC3Enhanced()

    mock_tool = MagicMock()
    mock_tool.handler = AsyncMock(return_value={"status": "success", "data": "test"})

    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_tool
    app._subsystems = {"mcp_registry": mock_registry}

    params = {"key": "value"}
    result = await app.call_mcp_tool("working_tool", params)

    assert result == {"status": "success", "data": "test"}
    mock_registry.get.assert_called_once_with("working_tool")
    mock_tool.handler.assert_called_once_with(params)

@pytest.mark.asyncio
async def test_call_mcp_tool_default_params():
    app = TRANC3Enhanced()

    mock_tool = MagicMock()
    mock_tool.handler = AsyncMock(return_value={"status": "success"})

    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_tool
    app._subsystems = {"mcp_registry": mock_registry}

    result = await app.call_mcp_tool("working_tool")

    assert result == {"status": "success"}
    mock_registry.get.assert_called_once_with("working_tool")
    mock_tool.handler.assert_called_once_with({})
