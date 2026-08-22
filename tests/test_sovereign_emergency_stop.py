import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from src.entities.tiers import Sovereign

class MockPrime:
    def __init__(self, id_val, should_fail=False):
        self.id = id_val
        self.stop = AsyncMock()
        if should_fail:
            self.stop.side_effect = Exception("Mocked Prime stop error")

class MockAI:
    def __init__(self, id_val, should_fail=False):
        self.id = id_val
        self.stop = AsyncMock()
        if should_fail:
            self.stop.side_effect = Exception("Mocked AI stop error")

@pytest.fixture
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

def test_sovereign_emergency_stop_logs_exceptions(event_loop):
    sov = Sovereign(sovereign_id="sov-1")

    prime_1 = MockPrime("p1", should_fail=True)
    prime_2 = MockPrime("p2", should_fail=False)

    ai_1 = MockAI("a1", should_fail=True)
    ai_2 = MockAI("a2", should_fail=False)

    sov.register_prime(prime_1)
    sov.register_prime(prime_2)

    sov.register_ai(ai_1)
    sov.register_ai(ai_2)

    with patch("src.entities.tiers.logger") as mock_logger:
        event_loop.run_until_complete(sov.emergency_stop())

        prime_1.stop.assert_called_once()
        prime_2.stop.assert_called_once()
        ai_1.stop.assert_called_once()
        ai_2.stop.assert_called_once()

        assert mock_logger.error.call_count == 2
        mock_logger.error.assert_any_call("Failed to stop Prime %s during emergency stop: %s", "p1", prime_1.stop.side_effect)
        mock_logger.error.assert_any_call("Failed to stop AI %s during emergency stop: %s", "a1", ai_1.stop.side_effect)
