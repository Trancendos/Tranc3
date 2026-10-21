## 2026-08-25 - Hardcoded Default Icecast Credentials
**Vulnerability:** Found hardcoded credentials (`icecast_admin_password: str = "hackme"`) and an unconfigurable URL (`icecast_url`) directly within `src/warp_radio/station.py`.
**Learning:** Hardcoded credentials exposed in source files pose a significant security risk, even if they are default or dummy values. Hardcoding these in the data model's default fields means developers could unintentionally deploy services with known default credentials that could be easily scraped or exploited if unmodified.
**Prevention:** Always use environment variables (e.g., `os.getenv(...)`) with fallback defaults for configurable sensitive data (like passwords, URLs, or API keys). Ensure secrets can be dynamically injected at runtime, complying with 12-factor application design principles.

## 2026-08-25 - Fix Sandbox Escape Vulnerability in MCP Tools
**Vulnerability:** The `_SAFE_BUILTINS` dictionary in `src/mcp/tools.py` for the `execute_code` sandboxed execution tool incorrectly included `"dir"`, `"getattr"`, and `"type"`, allowing for sandbox escapes and Arbitrary Code Execution (ACE) by traversing objects to retrieve hidden/sensitive references.
**Learning:** When defining restricted Python execution environments with `eval` or `exec`, it is crucial to exclude functions that enable introspection and attribute access. `dir`, `getattr`, and `type` can be chained to access un-sandboxed global state or classes and ultimately escape the sandbox.
**Prevention:** Strictly prohibit `getattr`, `dir`, and `type` from being passed into restricted sandbox environments. Maintain an allow-list of purely safe, functional built-ins, and regularly audit for powerful introspection functions.
