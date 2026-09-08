"""Emit low-risk runner diagnostics after a CI job fails."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess


def command_text(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        return f"unavailable: {exc}"
    return (result.stdout or result.stderr).strip()[-2000:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    print(f"## CI diagnostics: {args.job}")
    print(f"- Runner: {platform.platform()}")
    print(f"- Python: {command_text(['python', '--version'])}")
    print(f"- Git: {command_text(['git', 'rev-parse', '--short', 'HEAD'])}")
    print(f"- Disk free: {shutil.disk_usage(os.getcwd()).free // (1024**3)} GiB")
    print("- Working tree:")
    print("```text")
    print(command_text(["git", "status", "--short"]))
    print("```")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"\n## CI diagnostics: {args.job}\n")
            handle.write(f"- Runner: {platform.platform()}\n")
            handle.write(f"- Commit: {command_text(['git', 'rev-parse', '--short', 'HEAD'])}\n")
            handle.write(f"- Disk free: {shutil.disk_usage(os.getcwd()).free // (1024**3)} GiB\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
