import pytest
import asyncio
from unittest.mock import MagicMock, patch, ANY, AsyncMock
from src.main_enhanced import TRANC3Enhanced

@pytest.mark.asyncio
async def test_start_background_services_all_enabled():
    app = TRANC3Enhanced()
    app.config["healing"] = {"auto_repair": True}

    mock_monitor = MagicMock()
    app._subsystems["health_monitor"] = mock_monitor

    mock_tuner = MagicMock()
    app._subsystems["config_tuner"] = mock_tuner

    with patch("src.main_enhanced.asyncio.create_task") as mock_create_task:
        with patch.object(app, "_tuning_loop", MagicMock(return_value="mock_coro_tuning")) as mock_tuning_loop:
            mock_monitor.run_continuous.return_value = "mock_coro_monitor"

            await app.start_background_services()

            assert mock_create_task.call_count == 2
            mock_monitor.run_continuous.assert_called_once()
            mock_tuning_loop.assert_called_once_with(mock_tuner)

            mock_create_task.assert_any_call("mock_coro_monitor")
            mock_create_task.assert_any_call("mock_coro_tuning")

@pytest.mark.asyncio
async def test_start_background_services_auto_repair_false():
    app = TRANC3Enhanced()
    app.config["healing"] = {"auto_repair": False}

    mock_monitor = MagicMock()
    app._subsystems["health_monitor"] = mock_monitor

    mock_tuner = MagicMock()
    app._subsystems["config_tuner"] = mock_tuner

    with patch("src.main_enhanced.asyncio.create_task") as mock_create_task:
        with patch.object(app, "_tuning_loop", MagicMock(return_value="mock_coro_tuning")) as mock_tuning_loop:
            await app.start_background_services()

            assert mock_create_task.call_count == 1
            mock_monitor.run_continuous.assert_not_called()
            mock_tuning_loop.assert_called_once_with(mock_tuner)
            mock_create_task.assert_any_call("mock_coro_tuning")

@pytest.mark.asyncio
async def test_start_background_services_missing_subsystems():
    app = TRANC3Enhanced()
    app.config["healing"] = {"auto_repair": True}

    with patch("src.main_enhanced.asyncio.create_task") as mock_create_task:
        with patch.object(app, "_tuning_loop") as mock_tuning_loop:
            await app.start_background_services()

            assert mock_create_task.call_count == 0
            mock_tuning_loop.assert_not_called()
