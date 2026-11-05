## 2026-08-25 - Hardcoded Default Icecast Credentials
**Vulnerability:** Found hardcoded credentials (`icecast_admin_password: str = "hackme"`) and an unconfigurable URL (`icecast_url`) directly within `src/warp_radio/station.py`.
**Learning:** Hardcoded credentials exposed in source files pose a significant security risk, even if they are default or dummy values. Hardcoding these in the data model's default fields means developers could unintentionally deploy services with known default credentials that could be easily scraped or exploited if unmodified.
**Prevention:** Always use environment variables (e.g., `os.getenv(...)`) with fallback defaults for configurable sensitive data (like passwords, URLs, or API keys). Ensure secrets can be dynamically injected at runtime, complying with 12-factor application design principles.

## 2026-08-25 - Insecure JWT Base64 Fallback
**Vulnerability:** Found insecure fallback to base64 encoding/decoding for JWTs in `src/auth/tokens.py` when `python-jose` was not installed. This allowed attackers to forge access tokens by simply base64-encoding desired claims (e.g. admin privileges) and bypass authentication.
**Learning:** Never use `except ImportError` blocks to silently fall back to insecure implementations of critical security components. Applications must fail securely and raise an error rather than allowing authentication bypass when a dependency is missing.
**Prevention:** Always raise an explicit error when a required cryptographic or security library is missing (e.g. `raise RuntimeError("...") from None`). Do not try to shim or fallback to a custom or insecure implementation for authentication and authorization logic.
