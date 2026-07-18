# workers/notifications/error_handlers.py
# Vendored copy of Dimensional/error_handlers.py — see sanitize.py in this same
# directory for why. Keep in sync with Dimensional/error_handlers.py.
#
# Safe exception formatting for HTTP responses.
#
# Prevents information exposure (CWE-209) by ensuring that internal
# exception details (file paths, stack traces, database errors, etc.)
# are never included in API responses sent to clients.
#
# Usage:
#   from Dimensional.error_handlers import safe_error_detail, SafeHTTPException
#
#   # In route handlers:
#   except Exception:
#       raise HTTPException(status_code=500, detail=safe_error_detail())
#
#   # Or use the convenience class:
#   raise SafeHTTPException(status_code=500)

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# In production, we return generic messages. In development, we can be
# slightly more descriptive (but still never expose stack traces or
# internal paths).
_ENV = os.getenv("ENVIRONMENT", "development")
_IS_PROD = _ENV == "production"

# Mapping of common HTTP status codes to safe, user-facing messages
_SAFE_MESSAGES = {
    400: "Invalid request. Please check your input and try again.",
    401: "Authentication required.",
    403: "You do not have permission to perform this action.",
    404: "The requested resource was not found.",
    409: "The resource already exists or there is a conflict.",
    422: "Invalid input. Please check your request format.",
    429: "Rate limit exceeded. Please wait and try again.",
    500: "An internal error occurred. Please try again later.",
    502: "The service is temporarily unavailable.",
    503: "The service is currently unavailable. Please try again later.",
    504: "The request timed out. Please try again.",
}


def safe_error_detail(
    exc: Optional[Exception] = None,
    status_code: int = 500,
    *,
    log_reference: bool = True,
) -> str:
    """Return a safe, user-facing error message for HTTP responses.

    In production, this always returns a generic message based on the
    status code, never exposing the exception details.  In development,
    it includes a truncated version of the error for debugging, but
    still strips potentially sensitive information like file paths.

    Args:
        exc: The original exception (optional). If provided, its message
            is logged server-side but never sent to the client in production.
        status_code: The HTTP status code being returned.
        log_reference: If True, log the real error server-side with a
            reference ID for correlation.

    Returns:
        A safe string suitable for inclusion in an HTTP response body.
    """
    if exc is not None and log_reference:
        # Log the real error server-side for debugging
        import uuid

        ref_id = uuid.uuid4().hex[:8]
        # Use WARNING for 4xx client errors, ERROR for 5xx server errors
        log_fn = logger.warning if status_code < 500 else logger.error
        log_fn(
            "Error ref=%s status=%d: %s: %s",
            ref_id,
            status_code,
            type(exc).__name__,
            exc,
        )
        if _IS_PROD:
            return f"{_SAFE_MESSAGES.get(status_code, 'An error occurred.')} (ref: {ref_id})"
    elif _IS_PROD:
        return _SAFE_MESSAGES.get(status_code, "An error occurred.")

    # Development mode: include truncated error but sanitize file paths
    if exc is not None:
        raw_msg = str(exc)
        # Strip absolute file paths (common in Python tracebacks)
        import re

        sanitized = re.sub(
            r"(?:/home/|/usr/|/opt/|/var/|/etc/|/tmp/|C:\\)\S+",
            "[PATH]",
            raw_msg,
        )
        # Truncate to prevent oversized responses
        if len(sanitized) > 200:
            sanitized = sanitized[:200] + "..."
        return sanitized

    return _SAFE_MESSAGES.get(status_code, "An error occurred.")


class SafeHTTPException(HTTPException):
    """Convenience exception that automatically produces safe error details.

    Inherits from FastAPI's HTTPException so it is handled by the default
    exception handlers (returns proper JSON response with status code).

    Usage with FastAPI:
        from Dimensional.error_handlers import SafeHTTPException

        try:
            ...
        except SomeError as e:
            raise SafeHTTPException(status_code=500, exc=e)
    """

    def __init__(
        self,
        status_code: int = 500,
        exc: Optional[Exception] = None,
        headers: Optional[dict] = None,
    ):
        detail = safe_error_detail(exc, status_code)
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        super().__init__(self.detail)
