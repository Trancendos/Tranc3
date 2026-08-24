🧹 log exceptions instead of passing silently during emergency stop

🎯 **What:**
Instead of silently swallowing exceptions with `pass` during the `emergency_stop` method inside `src/entities/tiers.py`, the exceptions are now appropriately caught and logged using `logger.error()`.

💡 **Why:**
Silently suppressing exceptions makes debugging very difficult and masks potential errors that occur during emergency stop. By logging the error with the ID of the Prime/AI that failed to stop properly, we improve the maintainability and observability of the codebase.

✅ **Verification:**
Verified by running `pytest tests/test_models_governance_tiers.py` and checking with `ruff` to ensure correctness without regressions.

✨ **Result:**
Clearer diagnostics and logging outputs during emergency stops, retaining the exact same functional behavior while improving code health and debuggability.
