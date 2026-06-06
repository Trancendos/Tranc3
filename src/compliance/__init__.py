"""
DEFSTAN-inspired compliance framework for the Tranc3 / Trancendos platform.

Modules:
    checker          -- loads register.yaml, verifies evidence paths, scores compliance
    report_generator -- produces JSON, Markdown, and HTML reports
    traceability     -- builds requirement -> code -> test traceability matrix
    api_routes       -- FastAPI router exposing /compliance/* endpoints
"""

__version__ = "1.0.0"
