## 2026-08-25 - Hardcoded Default Icecast Credentials
**Vulnerability:** Found hardcoded credentials (`icecast_admin_password: str = "hackme"`) and an unconfigurable URL (`icecast_url`) directly within `src/warp_radio/station.py`.
**Learning:** Hardcoded credentials exposed in source files pose a significant security risk, even if they are default or dummy values. Hardcoding these in the data model's default fields means developers could unintentionally deploy services with known default credentials that could be easily scraped or exploited if unmodified.
**Prevention:** Always use environment variables (e.g., `os.getenv(...)`) with fallback defaults for configurable sensitive data (like passwords, URLs, or API keys). Ensure secrets can be dynamically injected at runtime, complying with 12-factor application design principles.
## 2024-10-09 - Sandbox Escape via Unsafe Python Built-ins
**Vulnerability:** The Python `_SAFE_BUILTINS` allowlist in `src/mcp/tools.py` included `dir`, `getattr`, and `type`.
**Learning:** Even in restricted execution environments, granting access to `type` allows traversing class hierarchies (e.g. `type.__subclasses__(type)` or via `getattr`), leading to arbitrary code execution and sandbox escapes.
**Prevention:** Strictly prohibit the inclusion of `getattr`, `dir`, and `type` when defining restricted Python sandboxes (e.g., via `_SAFE_BUILTINS` for `exec` or `eval`).
