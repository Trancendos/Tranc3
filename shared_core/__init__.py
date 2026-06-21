"""
shared_core — backward-compatibility shim.

All functionality has moved to Dimensional. This module re-exports
everything so existing imports continue to work unchanged.
"""

from Dimensional import *  # noqa: F401, F403
from Dimensional import (  # noqa: F401
    gas,
    genetics,
    liquid,
)
