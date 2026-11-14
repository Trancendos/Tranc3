## 2026-08-25 - Hardcoded Default Icecast Credentials
**Vulnerability:** Found hardcoded credentials (`icecast_admin_password: str = "hackme"`) and an unconfigurable URL (`icecast_url`) directly within `src/warp_radio/station.py`.
**Learning:** Hardcoded credentials exposed in source files pose a significant security risk, even if they are default or dummy values. Hardcoding these in the data model's default fields means developers could unintentionally deploy services with known default credentials that could be easily scraped or exploited if unmodified.
**Prevention:** Always use environment variables (e.g., `os.getenv(...)`) with fallback defaults for configurable sensitive data (like passwords, URLs, or API keys). Ensure secrets can be dynamically injected at runtime, complying with 12-factor application design principles.
## 2024-05-20 - Insecure JWT Fallback

**Vulnerability:** The application had an `except ImportError` block that silently fell back to insecure, unsigned base64 encoding when the `python-jose` dependency was missing.
**Learning:** Silently falling back to insecure implementations when a critical security dependency is missing allows authentication bypasses and breaks the principle of fail-safe defaults.
**Prevention:** Never use `except ImportError` blocks to silently fall back to insecure implementations. Applications must fail securely and raise an error rather than allowing authentication bypasses.
