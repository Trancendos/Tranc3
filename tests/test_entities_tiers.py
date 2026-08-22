import pytest
import asyncio
from src.entities.tiers import Sovereign, Prime, HILAApproval

def test_emergency_stop_logging(caplog):
    import logging
    caplog.set_level(logging.ERROR)

    sovereign = Sovereign("SOV-TEST", "Test Sovereign")

    class FailingPrime(Prime):
        async def stop(self):
            raise ValueError("prime stop failed")

    prime = FailingPrime("PRIME-TEST", "Test Prime")
    sovereign.register_prime(prime)

    class FailingAI:
        id = "AI-TEST"
        name = "Test AI"
        async def stop(self):
            raise RuntimeError("ai stop failed")

    ai = FailingAI()
    sovereign.register_ai(ai)

    asyncio.run(sovereign.emergency_stop())

    assert "Error stopping Prime PRIME-TEST: prime stop failed" in caplog.text
    assert "Error stopping AI AI-TEST: ai stop failed" in caplog.text
