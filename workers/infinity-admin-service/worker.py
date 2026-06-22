# Backwards-compatibility shim — uvicorn is configured to run `worker:app`.
# All implementation has been moved to the modular structure introduced in Phase 25+.
# See main.py, router.py, service.py, database.py, models.py, config.py.
from main import app  # noqa: F401
