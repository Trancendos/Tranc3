#!/usr/bin/env python3
"""
TRANC3 — Security Testing Script
Runs comprehensive security checks on the Tranc3 codebase.

Usage:
  python scripts/security_test.py --all
  python scripts/security_test.py --check-dependencies
  python scripts/security_test.py --check-code

Updated: 2025-07 — CVE Remediation
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_command(cmd: list, description: str) -> bool:
    """Run a command and return success status."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('='*60)

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        print(f"✅ {description} — PASSED")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} — FAILED")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return False


def check_dependencies() -> bool:
    """Check Python dependencies for vulnerabilities."""
    print("\n" + "="*60)
    print("DEPENDENCY VULNERABILITY SCANNING")
    print("="*60)

    all_passed = True

    # pip-audit
    all_passed &= run_command(
        ["pip", "audit", "-r", "requirements.txt"],
        "pip-audit (requirements.txt)"
    )

    # Check AI dependencies if they exist
    if Path("requirements-ai.txt").exists():
        all_passed &= run_command(
            ["pip", "audit", "-r", "requirements-ai.txt"],
            "pip-audit (requirements-ai.txt)"
        )

    # Safety check
    all_passed &= run_command(
        ["safety", "check", "-r", "requirements.txt"],
        "Safety check (requirements.txt)"
    )

    return all_passed


def check_code() -> bool:
    """Check Python code for security issues."""
    print("\n" + "="*60)
    print("CODE SECURITY ANALYSIS")
    print("="*60)

    all_passed = True

    # Bandit security linting
    all_passed &= run_command(
        ["bandit", "-r", "src/", "-f", "txt"],
        "Bandit security linting"
    )

    # Check for exact version pinning
    print("\nChecking for exact version pinning in requirements.txt...")
    with open("requirements.txt", "r") as f:
        lines = f.readlines()
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                if ">=" in line or "~=" in line or "*" in line:
                    print(f"⚠️  Non-exact version specifier found: {line}")
                    all_passed = False
    if all_passed:
        print("✅ All dependencies use exact version pinning")

    return all_passed


def check_docker() -> bool:
    """Check Docker configuration for security issues."""
    print("\n" + "="*60)
    print("DOCKER SECURITY CHECKS")
    print("="*60)

    all_passed = True

    # Check for non-root user
    print("\nChecking Dockerfile for non-root user...")
    dockerfile_path = Path("docker/Dockerfile")
    if dockerfile_path.exists():
        with open(dockerfile_path, "r") as f:
            content = f.read()
            if "USER" in content and "tranc3" in content:
                print("✅ Dockerfile uses non-root user")
            else:
                print("❌ Dockerfile may run as root")
                all_passed = False

            if "no-new-privileges" in content:
                print("✅ Dockerfile disables privilege escalation")
            else:
                print("⚠️  Dockerfile missing no-new-privileges")

    return all_passed


def check_secrets() -> bool:
    """Check for leaked secrets in the codebase."""
    print("\n" + "="*60)
    print("SECRET DETECTION")
    print("="*60)

    all_passed = True

    # Check for common secret patterns
    secret_patterns = [
        "password",
        "api_key",
        "secret",
        "token",
        "private_key",
    ]

    print("\nScanning for potential secrets...")
    for pattern in secret_patterns:
        result = subprocess.run(
            ["grep", "-r", "-i", pattern, "src/", "--include=*.py"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"⚠️  Found '{pattern}' in source code:")
            print(result.stdout[:500])  # Limit output

    print("✅ Secret detection scan complete")
    return all_passed


def generate_sbom() -> bool:
    """Generate Software Bill of Materials."""
    print("\n" + "="*60)
    print("SBOM GENERATION")
    print("="*60)

    return run_command(
        ["cyclonedx-py", "requirements", "-i", "requirements.txt", "-o", "sbom.json", "--format", "json"],
        "CycloneDX SBOM generation"
    )


def main():
    parser = argparse.ArgumentParser(description="Tranc3 Security Testing Script")
    parser.add_argument("--all", action="store_true", help="Run all security checks")
    parser.add_argument("--check-dependencies", action="store_true", help="Check dependencies")
    parser.add_argument("--check-code", action="store_true", help="Check code")
    parser.add_argument("--check-docker", action="store_true", help="Check Docker")
    parser.add_argument("--check-secrets", action="store_true", help="Check for secrets")
    parser.add_argument("--generate-sbom", action="store_true", help="Generate SBOM")

    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        sys.exit(1)

    all_passed = True

    if args.all or args.check_dependencies:
        all_passed &= check_dependencies()

    if args.all or args.check_code:
        all_passed &= check_code()

    if args.all or args.check_docker:
        all_passed &= check_docker()

    if args.all or args.check_secrets:
        all_passed &= check_secrets()

    if args.all or args.generate_sbom:
        all_passed &= generate_sbom()

    print("\n" + "="*60)
    if all_passed:
        print("✅ ALL SECURITY CHECKS PASSED")
        print("="*60)
        sys.exit(0)
    else:
        print("❌ SOME SECURITY CHECKS FAILED")
        print("="*60)
        sys.exit(1)


if __name__ == "__main__":
    main()