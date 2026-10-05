# Dimensionals/log_sanitize.py
# Compatibility shim — prefer Dimensionals.sanitize.sanitize_for_log directly.
#
# This module re-exports sanitize_for_log as sanitize_log for backward
# compatibility with any code that imported from here.

from Dimensionals.sanitize import sanitize_for_log as sanitize_log  # noqa: F401

__all__ = ["sanitize_log"]
