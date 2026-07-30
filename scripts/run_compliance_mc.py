#!/usr/bin/env python
"""Run the Magna Carta compliance check and print the markdown report.

Extracted from the Makefile's `compliance-mc` target so the logic lives in a
normal, lintable Python file instead of a single-line `python -c` string.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.compliance.checker import REGISTER_PATH, load_and_check_merged  # noqa: E402
from src.compliance.report_generator import generate_markdown  # noqa: E402


def main() -> None:
    magna_carta_register = Path(
        "compliance/magna-carta/compliance/magna_carta_register.yaml"
    )
    report = load_and_check_merged(REGISTER_PATH, magna_carta_register)
    print(generate_markdown(report))


if __name__ == "__main__":
    main()
