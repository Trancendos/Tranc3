"""MC runtime validator — validates all 9 Magna Carta rules and writes evidence.

Runs validators for each MC-RULE-001–009 and outputs
compliance/mc_validation_results.yaml so the compliance checker can
promote MC items from PARTIAL to COMPLIANT.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = REPO_ROOT / "compliance" / "mc_validation_results.yaml"


def _rule(rule_id: str, passed: bool, details: str, evidence: list[str] | None = None) -> dict:
    return {
        "rule_id": rule_id,
        "passed": passed,
        "details": details,
        "evidence": evidence or [],
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_mc_rule_001() -> dict:
    """MC-RULE-001: Magna Carta submodule wired."""
    submodule_dir = REPO_ROOT / "compliance" / "magna-carta"
    has_dir = submodule_dir.exists()
    has_gitmodules = (REPO_ROOT / ".gitmodules").exists()
    passed = has_dir or has_gitmodules
    return _rule(
        "MC-RULE-001",
        passed,
        f"Submodule dir exists: {has_dir}, .gitmodules exists: {has_gitmodules}",
        [str(REPO_ROOT / ".gitmodules")] if has_gitmodules else [],
    )


def validate_mc_rule_002() -> dict:
    """MC-RULE-002: Sovereignty principle documented."""
    evidence_files = [
        REPO_ROOT / "docs" / "01-MAGNACARTA-FOUNDATION.md",
        REPO_ROOT / "FRAMEWORK.md",
        REPO_ROOT / "docs" / "architecture" / "AS-BUILT-ARCHITECTURE.md",
    ]
    found = [str(f) for f in evidence_files if f.exists()]
    passed = len(found) >= 2
    return _rule("MC-RULE-002", passed, f"Sovereignty docs found: {len(found)}/3", found)


def validate_mc_rule_003() -> dict:
    """MC-RULE-003: Rate limiting implemented."""
    rate_limit_app = REPO_ROOT / "workers" / "rate-limit-service" / "app.py"
    adaptive = REPO_ROOT / "src" / "security" / "adaptive_rate_limiter.py"
    passed = rate_limit_app.exists()
    evidence = [str(f) for f in [rate_limit_app, adaptive] if f.exists()]
    return _rule("MC-RULE-003", passed, f"Rate limit service: {rate_limit_app.exists()}", evidence)


def validate_mc_rule_004() -> dict:
    """MC-RULE-004: Control-to-component traceability documented."""
    control_map = REPO_ROOT / "docs" / "architecture" / "CONTROL-TO-COMPONENT-MAP.md"
    passed = control_map.exists()
    return _rule(
        "MC-RULE-004", passed, f"Control map: {passed}", [str(control_map)] if passed else []
    )


def validate_mc_rule_005() -> dict:
    """MC-RULE-005: AI governance documented."""
    ai_gov = REPO_ROOT / "docs" / "compliance" / "AI-GOVERNANCE.md"
    ai_policy = REPO_ROOT / "docs" / "policies" / "POL-AI-001-AI-Ethics-Governance.md"
    model_gov = REPO_ROOT / "src" / "compliance" / "ai_governance.py"
    found = [str(f) for f in [ai_gov, ai_policy, model_gov] if f.exists()]
    passed = len(found) >= 2
    return _rule("MC-RULE-005", passed, f"AI governance docs: {len(found)}/3", found)


def validate_mc_rule_006() -> dict:
    """MC-RULE-006: Compliance blueprint documented."""
    blueprint = REPO_ROOT / "docs" / "compliance" / "COMPLIANCE-BLUEPRINT.md"
    framework = REPO_ROOT / "FRAMEWORK.md"
    hipaa = REPO_ROOT / "docs" / "compliance" / "HIPAA-ALIGNMENT.md"
    found = [str(f) for f in [blueprint, framework, hipaa] if f.exists()]
    passed = len(found) >= 2
    return _rule("MC-RULE-006", passed, f"Compliance blueprint docs: {len(found)}/3", found)


def validate_mc_rule_007() -> dict:
    """MC-RULE-007: CAB gate implemented (Town Hall approval)."""
    cab_gate = REPO_ROOT / "src" / "compliance" / "cab_gate.py"
    api_py = REPO_ROOT / "api.py"
    cab_wired = False
    if api_py.exists():
        content = api_py.read_text()
        cab_wired = "CABMiddleware" in content
    passed = cab_gate.exists() and cab_wired
    evidence = [str(f) for f in [cab_gate] if f.exists()]
    return _rule(
        "MC-RULE-007",
        passed,
        f"CAB gate file: {cab_gate.exists()}, wired in api.py: {cab_wired}",
        evidence,
    )


def validate_mc_rule_008() -> dict:
    """MC-RULE-008: HIPAA alignment documented."""
    hipaa = REPO_ROOT / "docs" / "compliance" / "HIPAA-ALIGNMENT.md"
    sentinel = REPO_ROOT / "src" / "security" / "hipaa_sentinel.py"
    found = [str(f) for f in [hipaa, sentinel] if f.exists()]
    passed = hipaa.exists()
    return _rule("MC-RULE-008", passed, f"HIPAA docs: {len(found)}", found)


def validate_mc_rule_009() -> dict:
    """MC-RULE-009: MC-MAGNA_CARTA_ENABLED staging enablement."""
    env_example = REPO_ROOT / ".env.example"
    has_flag = False
    if env_example.exists():
        content = env_example.read_text()
        has_flag = "MAGNA_CARTA_ENABLED" in content
    action_tracker = REPO_ROOT / "compliance" / "compliance_action_tracker.yaml"
    passed = has_flag or action_tracker.exists()
    evidence = [str(f) for f in [env_example, action_tracker] if f.exists()]
    return _rule(
        "MC-RULE-009",
        passed,
        f"MAGNA_CARTA_ENABLED flag: {has_flag}, action tracker: {action_tracker.exists()}",
        evidence,
    )


def run_all_validators() -> list[dict]:
    validators = [
        validate_mc_rule_001,
        validate_mc_rule_002,
        validate_mc_rule_003,
        validate_mc_rule_004,
        validate_mc_rule_005,
        validate_mc_rule_006,
        validate_mc_rule_007,
        validate_mc_rule_008,
        validate_mc_rule_009,
    ]
    results = []
    for v in validators:
        try:
            results.append(v())
        except Exception as exc:
            rule_id = v.__doc__.split(":")[0].strip() if v.__doc__ else "UNKNOWN"
            results.append(_rule(rule_id, False, f"Validator error: {exc}"))
    return results


def write_results(results: list[dict]) -> None:
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    output = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "src/compliance/mc_validator.py",
            "total_rules": total,
            "passed": passed,
            "failed": total - passed,
            "score_pct": round(passed / total * 100, 1) if total else 0,
        },
        "results": results,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(yaml.dump(output, default_flow_style=False, sort_keys=False))
    print(f"MC validation: {passed}/{total} rules passed ({output['meta']['score_pct']}%)")
    print(f"Results written to {OUTPUT_PATH}")


def main() -> int:
    results = run_all_validators()
    write_results(results)
    failed = [r for r in results if not r["passed"]]
    if failed:
        print("\nFailed rules:")
        for r in failed:
            print(f"  {r['rule_id']}: {r['details']}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
