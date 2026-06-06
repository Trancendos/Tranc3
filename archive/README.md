# Archive

Legacy entry-point files moved here as part of TR3-003 API canonicalization.

| File | Archived | Successor |
|------|----------|-----------|
| `api_ecosystem.py` | 2026-06-06 | `src/routers/ecosystem.py` (included in `api.py`) |
| `api_enhanced.py` | 2026-06-06 | `src/routers/enhanced_capabilities.py` (included in `api.py`) |

## Canonical entry point

**`api.py`** is the single authoritative FastAPI application.
All routes from both archived files are registered in `api.py` via their respective routers.

Do not add new files here. Do not extend archived files.
