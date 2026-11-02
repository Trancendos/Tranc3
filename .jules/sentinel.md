## 2026-08-25 - Hardcoded Default Icecast Credentials
**Vulnerability:** Found hardcoded credentials (`icecast_admin_password: str = "hackme"`) and an unconfigurable URL (`icecast_url`) directly within `src/warp_radio/station.py`.
**Learning:** Hardcoded credentials exposed in source files pose a significant security risk, even if they are default or dummy values. Hardcoding these in the data model's default fields means developers could unintentionally deploy services with known default credentials that could be easily scraped or exploited if unmodified.
**Prevention:** Always use environment variables (e.g., `os.getenv(...)`) with fallback defaults for configurable sensitive data (like passwords, URLs, or API keys). Ensure secrets can be dynamically injected at runtime, complying with 12-factor application design principles.

## 2026-10-26 - Insecure JWT Encoding/Decoding Fallback
**Vulnerability:** Found `except ImportError` blocks in `src/auth/tokens.py` that silently fall back to unverified base64 encoding/decoding if the `jose` dependency is missing. This allows authentication bypass if the environment is incorrectly configured.
**Learning:** Applications must fail securely and raise an error rather than allowing authentication bypasses by falling back to insecure implementations when a critical security dependency is missing.
**Prevention:** Never use `except ImportError` blocks to silently fall back to insecure implementations (such as unverified base64 encoding instead of properly signed JWTs). Raise explicit `RuntimeError` or similar exceptions.
