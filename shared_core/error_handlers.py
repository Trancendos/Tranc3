"""
Re-exports from Dimensional.error_handlers — single source of truth lives there.

All imports of ``from shared_core.error_handlers import ...`` continue to work
transparently. The Dimensional package is kept canonical because the security
automation remediator scripts hard-code that import path.
"""

from Dimensional.error_handlers import *  # noqa: F401, F403
from Dimensional.error_handlers import SafeHTTPException, safe_error_detail  # noqa: F401
