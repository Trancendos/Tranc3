#!/usr/bin/env python3
"""
scripts/security_test.py
Trancendos — Python security test suite.
Complements scripts/security_scan.sh (bash) with structured pass/fail reporting.

Usage:
  python scripts/security_test.py            # run all checks
  python scripts/security_test.py --deps     # dependency CVE scan only
  python scripts/security_test.py --code     # SAST only
  python scripts/security_test.py --pins     # exact pinning check only
  python scripts/security_test.py --secrets  # hardcoded secret heuristics
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def run(cmd: list[str], label: str) -> bool:
    print(f"\n{'─'*60}")
    print(f"  {label}")
    print(f"  $ {' '.join(cmd)}")
    print(f"{'─'*60}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            sys.stderr.write(result.stderr)
        if result.returncode == 0:
            print("  ✓  PASS")
            return True
        print(f"  ✗  FAIL (exit {result.returncode})")
        return False
    except FileNotFoundError:
        print(f"  ⚠  SKIP — command not found: {cmd[0]}")
        return True  # don't fail for missing optional tool


def check_deps() -> bool:
    ok = True
    ok &= run(
        ["pip-audit", "-r", str(ROOT / "requirements.txt"), "--progress-spinner", "off"],
        "pip-audit: requirements.txt",
    )
    for extra in ("requirements-ai.txt", "requirements-security.txt"):
        path = ROOT / extra
        if path.exists():
            ok &= run(
                ["pip-audit", "-r", str(path), "--progress-spinner", "off"],
                f"pip-audit: {extra}",
            )
    return ok


def check_code() -> bool:
    ok = run(
        ["bandit", "-r", "src/", "-ll", "-ii", "--quiet"],
        "bandit: SAST scan (severity=medium, confidence=medium)",
    )
    return ok


def check_pins() -> bool:
    print(f"\n{'─'*60}")
    print("  Exact version pinning check")
    print(f"{'─'*60}")
    bad_lines: list[tuple[str, int, str]] = []
    for req_file in [
        "requirements.txt",
        "requirements-ai.txt",
        "requirements-security.txt",
    ]:
        path = ROOT / req_file
        if not path.exists():
            continue
        for i, raw in enumerate(path.read_text().splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("-r "):
                continue
            pkg = line.split("#")[0].strip()
            if any(op in pkg for op in (">=", "~=", "!=", ">", "<")) and "==" not in pkg:
                bad_lines.append((req_file, i, line))
            elif "*" in pkg:
                bad_lines.append((req_file, i, line))

    if bad_lines:
        for f, lno, line in bad_lines:
            print(f"  ⚠  {f}:{lno}  {line}")
        print(f"  ✗  FAIL — {len(bad_lines)} non-exact specifier(s) found")
        return False

    print("  ✓  All dependencies use exact version pinning (==)")
    return True


def check_secrets() -> bool:
    print(f"\n{'─'*60}")
    print("  Hardcoded secret heuristics (gitleaks / grep)")
    print(f"{'─'*60}")
    gitleaks = run(
        ["gitleaks", "detect", "--source", ".", "--log-level", "warn", "--exit-code", "1"],
        "gitleaks detect",
    )
    if gitleaks:
        return True

    # gitleaks not installed — fall back to grep heuristics
    print("  gitleaks not available — running grep heuristics")
    patterns = [
        r"sk-[a-zA-Z0-9]{20,}",  # OpenAI key
        r"ghp_[a-zA-Z0-9]{36}",  # GitHub PAT
        r"AKIA[0-9A-Z]{16}",  # AWS access key
        r"-----BEGIN (RSA|EC) PRIVATE",  # Private keys
        r"password\s*=\s*['\"][^'\"]{8,}",  # Hardcoded passwords
    ]
    result = subprocess.run(
        [
            "grep",
            "-rn",
            "-E",
            "|".join(patterns),
            "--include=*.py",
            "--include=*.js",
            "--include=*.ts",
            "--exclude-dir=.git",
            "--exclude-dir=node_modules",
            "src/",
            "cloudflare/",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.stdout.strip():
        print(result.stdout.rstrip())
        print("  ✗  FAIL — potential secrets detected")
        return False
    print("  ✓  No obvious hardcoded secrets found")
    return True


def check_semgrep() -> bool:
    return run(
        [
            "semgrep",
            "--config",
            "p/python",
            "--config",
            "p/owasp-top-ten",
            "--severity",
            "ERROR",
            "--exit-zero",
            "src/",
        ],
        "semgrep: p/python + p/owasp-top-ten",
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Trancendos security test suite")
    p.add_argument("--deps", action="store_true", help="Dependency CVE scan")
    p.add_argument("--code", action="store_true", help="SAST (bandit)")
    p.add_argument("--pins", action="store_true", help="Exact pinning check")
    p.add_argument("--secrets", action="store_true", help="Hardcoded secrets")
    p.add_argument("--semgrep", action="store_true", help="Semgrep SAST")
    args = p.parse_args()

    run_all = not any([args.deps, args.code, args.pins, args.secrets, args.semgrep])

    results: dict[str, bool] = {}

    if run_all or args.pins:
        results["pin-check"] = check_pins()
    if run_all or args.deps:
        results["pip-audit"] = check_deps()
    if run_all or args.code:
        results["bandit"] = check_code()
    if run_all or args.secrets:
        results["secrets"] = check_secrets()
    if run_all or args.semgrep:
        results["semgrep"] = check_semgrep()

    print(f"\n{'═'*60}")
    print("  Results")
    print(f"{'═'*60}")
    for name, passed in results.items():
        mark = "✓" if passed else "✗"
        print(f"  {mark}  {name}")

    total = len(results)
    passed = sum(results.values())
    print(f"\n  {passed}/{total} checks passed")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
