## 2026-08-25 - Hardcoded Default Icecast Credentials
**Vulnerability:** Found hardcoded credentials (`icecast_admin_password: str = "hackme"`) and an unconfigurable URL (`icecast_url`) directly within `src/warp_radio/station.py`.
**Learning:** Hardcoded credentials exposed in source files pose a significant security risk, even if they are default or dummy values. Hardcoding these in the data model's default fields means developers could unintentionally deploy services with known default credentials that could be easily scraped or exploited if unmodified.
**Prevention:** Always use environment variables (e.g., `os.getenv(...)`) with fallback defaults for configurable sensitive data (like passwords, URLs, or API keys). Ensure secrets can be dynamically injected at runtime, complying with 12-factor application design principles.

## 2024-10-13 - Authentication Bypass via Missing Dependency Fallback
**Vulnerability:** The `src/auth/tokens.py` module had an `except ImportError` block that fell back to generating unverified, unsigned `base64` encoded strings instead of secure JWTs if the `jose` dependency was missing. Unauthenticated users could easily forge these base64 tokens, leading to an authentication bypass.
**Learning:** Silently falling back to insecure or mock implementations when security-critical dependencies (like `jose` for JWTs) are missing introduces critical vulnerabilities that fail open instead of failing securely.
**Prevention:** Never use `except ImportError` to provide insecure, unverified fallbacks for critical security operations. If a required security library is unavailable, the application should fail securely (e.g., raise an exception or crash) rather than degrade to an insecure state.
