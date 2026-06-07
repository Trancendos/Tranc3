"""
13-Gate Compliance Lifecycle — DEFSTAN-Aligned Quality Gates
=============================================================
Rule-based (no LLM) implementation of 13 project gates adapted to the
Tranc3/Trancendos codebase.  Each gate inspects the repository structure
and produces a scored, pass/fail result.

Inspired by: the-observatory gateComplianceSystem.ts
Zero-cost: Pure Python stdlib. No external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# ── Data structures ────────────────────────────────────────────────────────────


@dataclass
class GateResult:
    gate_number: int
    gate_name: str
    passed: bool
    score: int  # 0-100
    findings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Gate implementations ───────────────────────────────────────────────────────


def _files_exist(root: Path, *paths: str) -> list[str]:
    """Return list of paths that exist (relative to *root*)."""
    return [p for p in paths if (root / p).exists()]


def _files_missing(root: Path, *paths: str) -> list[str]:
    return [p for p in paths if not (root / p).exists()]


def _count_glob(root: Path, pattern: str) -> int:
    return len(list(root.glob(pattern)))


def _gate(number: int, name: str) -> Callable:
    """Decorator that annotates a gate function with its number and name."""

    def decorator(fn: Callable) -> Callable:
        fn._gate_number = number
        fn._gate_name = name
        return fn

    return decorator


@_gate(0, "Project Initiation")
def gate_0(root: Path) -> GateResult:
    findings: list[str] = []
    blockers: list[str] = []
    score = 0

    if (root / "CLAUDE.md").exists():
        findings.append("CLAUDE.md present (objectives/scope defined)")
        score += 40
    else:
        blockers.append("CLAUDE.md missing — project scope undefined")

    if (root / "PLATFORM_ENTITIES.md").exists():
        findings.append("PLATFORM_ENTITIES.md present (entity catalogue defined)")
        score += 30
    else:
        findings.append("PLATFORM_ENTITIES.md not found")

    if (root / "pyproject.toml").exists():
        findings.append("pyproject.toml present")
        score += 30
    else:
        blockers.append("pyproject.toml missing — project not initialised")

    return GateResult(
        gate_number=0,
        gate_name="Project Initiation",
        passed=len(blockers) == 0 and score >= 60,
        score=score,
        findings=findings,
        blockers=blockers,
    )


@_gate(1, "Requirements Validation")
def gate_1(root: Path) -> GateResult:
    findings: list[str] = []
    blockers: list[str] = []
    score = 0

    register = root / "compliance" / "register.yaml"
    if register.exists():
        text = register.read_text(errors="replace")
        req_count = text.count("  - id: REQ-")
        findings.append(f"compliance/register.yaml has ~{req_count} requirements")
        score = min(100, 50 + req_count * 2)
        if req_count == 0:
            blockers.append("Compliance register is empty — add at least one REQ")
    else:
        blockers.append("compliance/register.yaml missing")

    return GateResult(
        gate_number=1,
        gate_name="Requirements Validation",
        passed=len(blockers) == 0 and score >= 50,
        score=score,
        findings=findings,
        blockers=blockers,
    )


@_gate(2, "Technical Feasibility")
def gate_2(root: Path) -> GateResult:
    findings: list[str] = []
    blockers: list[str] = []
    score = 0

    key_paths = [
        "src/core",
        "src/mesh",
        "src/auth",
        "src/workflow",
        "src/mcp",
        "api.py",
    ]
    found = _files_exist(root, *key_paths)
    missing = _files_missing(root, *key_paths)
    score = int(len(found) / len(key_paths) * 100)
    findings.append(f"Core modules present: {', '.join(found)}")
    if missing:
        findings.append(f"Core modules absent: {', '.join(missing)}")
    if score < 50:
        blockers.append("Less than half of key source modules exist")

    return GateResult(
        gate_number=2,
        gate_name="Technical Feasibility",
        passed=score >= 70,
        score=score,
        findings=findings,
        blockers=blockers,
    )


@_gate(3, "Design & UX Validation")
def gate_3(root: Path) -> GateResult:
    findings: list[str] = []
    blockers: list[str] = []
    score = 0

    if (root / "web").exists():
        findings.append("web/ directory present")
        score += 50
    else:
        findings.append("web/ directory absent (frontend not yet built)")

    if (root / "web" / "src").exists():
        findings.append("web/src/ present")
        score += 30
    if _count_glob(root, "web/**/*.tsx") > 0 or _count_glob(root, "web/**/*.ts") > 0:
        findings.append("TypeScript/React source files found in web/")
        score += 20

    return GateResult(
        gate_number=3,
        gate_name="Design & UX Validation",
        passed=score >= 50,
        score=min(score, 100),
        findings=findings,
        blockers=blockers,
    )


@_gate(4, "Development Standards")
def gate_4(root: Path) -> GateResult:
    findings: list[str] = []
    blockers: list[str] = []
    score = 0

    if (root / "pyproject.toml").exists():
        text = (root / "pyproject.toml").read_text(errors="replace")
        if "[tool.ruff]" in text or "ruff" in text:
            findings.append("ruff configured in pyproject.toml")
            score += 40
        else:
            findings.append("pyproject.toml exists but no ruff config")
            score += 20
    else:
        blockers.append("pyproject.toml missing")

    if (root / ".pre-commit-config.yaml").exists():
        findings.append(".pre-commit-config.yaml present")
        score += 30

    if (root / "Makefile").exists():
        findings.append("Makefile present")
        score += 30

    return GateResult(
        gate_number=4,
        gate_name="Development Standards",
        passed=len(blockers) == 0 and score >= 60,
        score=min(score, 100),
        findings=findings,
        blockers=blockers,
    )


@_gate(5, "Code Quality & Testing")
def gate_5(root: Path) -> GateResult:
    findings: list[str] = []
    blockers: list[str] = []

    tests_dir = root / "tests"
    if not tests_dir.exists():
        blockers.append("tests/ directory missing")
        return GateResult(
            gate_number=5,
            gate_name="Code Quality & Testing",
            passed=False,
            score=0,
            findings=findings,
            blockers=blockers,
        )

    test_files = list(tests_dir.glob("test_*.py"))
    count = len(test_files)
    findings.append(f"Found {count} test file(s) in tests/")
    score = min(100, count * 10)

    if count == 0:
        blockers.append("No test files found in tests/")
    elif count < 3:
        findings.append("Recommend adding more test coverage")

    return GateResult(
        gate_number=5,
        gate_name="Code Quality & Testing",
        passed=count >= 3,
        score=score,
        findings=findings,
        blockers=blockers,
    )


@_gate(6, "Security Review")
def gate_6(root: Path) -> GateResult:
    findings: list[str] = []
    blockers: list[str] = []
    score = 0

    security_files = {
        "src/auth/zero_trust.py": 40,
        "src/security": 30,
        "ARCHITECTURE_THREAT_MODEL.md": 30,
    }
    for path, weight in security_files.items():
        if (root / path).exists():
            findings.append(f"{path} present")
            score += weight
        else:
            findings.append(f"{path} not found")

    if score < 40:
        blockers.append("Core security components (zero_trust.py) missing")

    return GateResult(
        gate_number=6,
        gate_name="Security Review",
        passed=score >= 60,
        score=min(score, 100),
        findings=findings,
        blockers=blockers,
    )


@_gate(7, "Performance & Scalability")
def gate_7(root: Path) -> GateResult:
    findings: list[str] = []
    score = 0

    checks = {
        "src/mesh/circuit_breaker.py": 25,
        "src/mesh/bulkhead.py": 25,
        "src/mesh/rate_limiter.py": 25,
        "src/mesh/service_mesh.py": 25,
    }
    for path, weight in checks.items():
        if (root / path).exists():
            findings.append(f"{path} present")
            score += weight
        else:
            findings.append(f"{path} absent")

    return GateResult(
        gate_number=7,
        gate_name="Performance & Scalability",
        passed=score >= 50,
        score=min(score, 100),
        findings=findings,
        blockers=[],
    )


@_gate(8, "Documentation")
def gate_8(root: Path) -> GateResult:
    findings: list[str] = []
    score = 0

    if (root / "docs").exists():
        findings.append("docs/ directory present")
        score += 40
        doc_files = _count_glob(root, "docs/**/*.md")
        findings.append(f"{doc_files} markdown files in docs/")
        score += min(40, doc_files * 5)
    else:
        findings.append("docs/ directory absent")

    if (root / "CLAUDE.md").exists():
        findings.append("CLAUDE.md (developer guide) present")
        score += 20

    return GateResult(
        gate_number=8,
        gate_name="Documentation",
        passed=score >= 50,
        score=min(score, 100),
        findings=findings,
        blockers=[],
    )


@_gate(9, "Security Deep Dive")
def gate_9(root: Path) -> GateResult:
    findings: list[str] = []
    score = 0

    if (root / ".pre-commit-config.yaml").exists():
        text = (root / ".pre-commit-config.yaml").read_text(errors="replace")
        tools = []
        for tool in ("bandit", "semgrep", "gitleaks", "detect-secrets", "safety"):
            if tool in text:
                tools.append(tool)
        findings.append(f"Security tools in pre-commit: {', '.join(tools) or 'none'}")
        score = min(100, len(tools) * 20)
    else:
        findings.append(".pre-commit-config.yaml missing — no SAST gate configured")
        score = 10

    return GateResult(
        gate_number=9,
        gate_name="Security Deep Dive",
        passed=score >= 60,
        score=score,
        findings=findings,
        blockers=[],
    )


@_gate(10, "Cost Validation")
def gate_10(root: Path) -> GateResult:
    findings: list[str] = []
    score = 0

    env_example = root / ".env.example"
    if env_example.exists():
        text = env_example.read_text(errors="replace")
        findings.append(".env.example present")
        score += 50
        if "PLATFORM_INFRA_MODE" in text:
            findings.append("PLATFORM_INFRA_MODE defined in .env.example")
            score += 50
        else:
            findings.append("PLATFORM_INFRA_MODE not set in .env.example")
    else:
        findings.append(".env.example absent")

    if (root / "src" / "monitoring" / "zero_cost_tracker.py").exists():
        findings.append("Zero-cost tracker implemented")
        score = min(100, score + 20)

    return GateResult(
        gate_number=10,
        gate_name="Cost Validation",
        passed=score >= 50,
        score=min(score, 100),
        findings=findings,
        blockers=[],
    )


@_gate(11, "Deployment Readiness")
def gate_11(root: Path) -> GateResult:
    findings: list[str] = []
    blockers: list[str] = []
    score = 0

    deploy_artefacts = {
        "fly.toml": 30,
        "docker-compose.production.yml": 40,
        "deploy": 30,
    }
    for path, weight in deploy_artefacts.items():
        if (root / path).exists():
            findings.append(f"{path} present")
            score += weight
        else:
            findings.append(f"{path} absent")

    if score < 30:
        blockers.append("No deployment artefacts found (fly.toml or docker-compose.production.yml)")

    return GateResult(
        gate_number=11,
        gate_name="Deployment Readiness",
        passed=score >= 60,
        score=min(score, 100),
        findings=findings,
        blockers=blockers,
    )


@_gate(12, "Production Monitoring")
def gate_12(root: Path) -> GateResult:
    findings: list[str] = []
    score = 0

    if (root / "src" / "observability").exists():
        findings.append("src/observability/ present")
        score += 50
        obs_files = _count_glob(root, "src/observability/*.py")
        score += min(30, obs_files * 10)
        findings.append(f"{obs_files} observability modules")
    else:
        findings.append("src/observability/ absent")

    if (root / "monitoring").exists():
        findings.append("monitoring/ directory present (Prometheus/Grafana)")
        score += 20

    return GateResult(
        gate_number=12,
        gate_name="Production Monitoring",
        passed=score >= 50,
        score=min(score, 100),
        findings=findings,
        blockers=[],
    )


# ── Runner ────────────────────────────────────────────────────────────────────

_GATE_FUNCTIONS = [
    gate_0,
    gate_1,
    gate_2,
    gate_3,
    gate_4,
    gate_5,
    gate_6,
    gate_7,
    gate_8,
    gate_9,
    gate_10,
    gate_11,
    gate_12,
]


class GateLifecycleRunner:
    """Runs all 13 compliance gates against a repository root."""

    def run_all_gates(self, repo_root: Path) -> list[GateResult]:
        return [fn(repo_root) for fn in _GATE_FUNCTIONS]

    def run_gate(self, gate_number: int, repo_root: Path) -> GateResult:
        if gate_number < 0 or gate_number >= len(_GATE_FUNCTIONS):
            raise ValueError(f"Gate number must be 0-{len(_GATE_FUNCTIONS) - 1}")
        return _GATE_FUNCTIONS[gate_number](repo_root)

    def get_lifecycle_report(self, results: list[GateResult]) -> dict:
        passed = sum(1 for r in results if r.passed)
        total = len(results)
        avg_score = sum(r.score for r in results) / total if total else 0
        return {
            "total_gates": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total * 100, 1) if total else 0,
            "avg_score": round(avg_score, 1),
            "gates": [
                {
                    "number": r.gate_number,
                    "name": r.gate_name,
                    "passed": r.passed,
                    "score": r.score,
                    "blockers": r.blockers,
                }
                for r in results
            ],
        }


# ── CLI entry-point ────────────────────────────────────────────────────────────


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Tranc3 13-Gate Compliance Lifecycle")
    parser.add_argument("--repo", default=".", help="Path to repository root")
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    runner = GateLifecycleRunner()
    results = runner.run_all_gates(root)

    # Print table
    header = f"{'Gate':<6} {'Name':<35} {'Pass':^6} {'Score':^7}"
    print(header)
    print("-" * len(header))
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"{r.gate_number:<6} {r.gate_name:<35} {status:^6} {r.score:^7}")
        for b in r.blockers:
            print(f"       ⚠  BLOCKER: {b}")

    report = runner.get_lifecycle_report(results)
    print()
    print(
        f"Overall: {report['passed']}/{report['total_gates']} gates passed "
        f"({report['pass_rate']}%) — avg score {report['avg_score']}"
    )


if __name__ == "__main__":
    _cli()


__all__ = [
    "GateLifecycleRunner",
    "GateResult",
]
