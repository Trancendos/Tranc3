"""Retry dependency and tool bootstrap commands only when failure is transient."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time

TRANSIENT_PATTERNS = (
    r"timed out",
    r"temporary failure",
    r"connection reset",
    r"connection aborted",
    r"name or service not known",
    r"502 bad gateway",
    r"503 service unavailable",
    r"429 too many requests",
    r"rate limit",
    r"could not resolve host",
)


def classify(output: str, returncode: int) -> str:
    if returncode == 0:
        return "success"
    if any(re.search(pattern, output, re.IGNORECASE) for pattern in TRANSIENT_PATTERNS):
        return "transient"
    return "deterministic"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")

    attempts = max(1, min(args.attempts, 3))
    for attempt in range(1, attempts + 1):
        print(f"::group::{args.label} attempt {attempt}/{attempts}")
        completed = subprocess.run(command, text=True, capture_output=True)
        output = f"{completed.stdout}\n{completed.stderr}"
        print(output, end="")
        classification = classify(output, completed.returncode)
        print("::endgroup::")
        print(f"CI command classification: {classification}")
        if completed.returncode == 0:
            return 0
        if classification != "transient" or attempt == attempts:
            print(
                f"::error title={args.label} failed::classification={classification}; "
                "deterministic failures are not suppressed"
            )
            return completed.returncode or 1
        delay = 2**attempt
        print(f"::warning::Transient {args.label} failure; retrying in {delay}s")
        time.sleep(delay)

    return 1


if __name__ == "__main__":
    sys.exit(main())
