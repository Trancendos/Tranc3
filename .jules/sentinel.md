## 2026-08-25 - Hardcoded Default Icecast Credentials
**Vulnerability:** Found hardcoded credentials (`icecast_admin_password: str = "hackme"`) and an unconfigurable URL (`icecast_url`) directly within `src/warp_radio/station.py`.
**Learning:** Hardcoded credentials exposed in source files pose a significant security risk, even if they are default or dummy values. Hardcoding these in the data model's default fields means developers could unintentionally deploy services with known default credentials that could be easily scraped or exploited if unmodified.
**Prevention:** Always use environment variables (e.g., `os.getenv(...)`) with fallback defaults for configurable sensitive data (like passwords, URLs, or API keys). Ensure secrets can be dynamically injected at runtime, complying with 12-factor application design principles.
## 2025-02-14 - Sandbox Escape via Dangerous Built-ins
**Vulnerability:** The restricted execution sandbox for MCP tools (`execute_code` in `src/mcp/tools.py`) allowed `dir`, `getattr`, and `type` in its `_SAFE_BUILTINS` list.
**Learning:** Even in restricted environments, reflection and introspection functions can be chained to traverse the object graph and escape the sandbox (e.g., retrieving `__class__.__subclasses__()`).
**Prevention:** Strictly prohibit all reflection built-ins (`getattr`, `dir`, `type`) when defining constrained sandboxes for `exec` or `eval`. Use a tightly curated allowlist rather than a denylist.
