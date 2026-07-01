# shared_core/error_handlers.py
# Re-exports from Dimensional.error_handlers — single source of truth lives there.
# All imports of `from shared_core.error_handlers import ...` continue to work.
from Dimensional.error_handlers import *  # noqa: F401, F403
from Dimensional.error_handlers import safe_error_detail, SafeHTTPException  # noqa: F401
