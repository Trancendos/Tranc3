"""
shared_core — backward-compatibility shim.

All functionality has moved to Dimensionals. This module re-exports
everything so existing imports continue to work unchanged.
"""

from Dimensionals import *  # noqa: F401, F403
from Dimensionals import (  # noqa: F401
    gas,
    genetics,
    liquid,
)
