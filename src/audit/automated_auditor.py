"""Automated compliance auditor and remediation engine.

Runs on a background schedule to:
1. Validate compliance register evidence paths
2. Run MC rule validators
3. Perform security posture checks
4. Auto-remediate simple issues (backup, secret rotation triggers)
5. Write audit results to compliance/audit_results.yaml
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("automated_auditor")

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_OUTPUT = REPO_ROOT / "compliance" / "audit_results.yaml"
REGISTER_PATH = REPO_ROOT / "compliance" / "register.yaml"
AUDIT_INTERVAL_HOURS = int(os.getenv("AUDIT_INTERVAL_HOURS", "24"))


class AuditFinding:
    def __init__(self, check: str, status: str, detail: str, auto_remediated: bool = False) -> None:
        self.check = check
        self.status = status  # PASS | WARN | FAIL
        self.detail = detail
        self.auto_remediated = auto_remediated
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "check": self.check,
            "status": self.status,
            "detail": self.detail,
            "auto_remediated": self.auto_remediated,
            "timestamp": self.timestamp,
        }


class AutomatedAuditor:
    """Runs automated compliance and security audits with remediation."""

    def __init__(self) -> None:
        self._findings: list[AuditFinding] = []

    def _finding(self, check: str, status: str, detail: str, auto_remediated: bool = False) -> AuditFinding:
        f = AuditFinding(check, status, detail, auto_remediated)
        self._findings.append(f)
        log_fn = logger.info if status == "PASS" else (logger.warning if status == "WARN" else logger.error)
        log_fn("[%s] %s: %s", status, check, detail)
        return f

    # ── Compliance Register Audit ─────────────────────────────────────────────

    def audit_register_evidence(self) -> list[AuditFinding]:
        """Check all evidence paths in compliance register exist."""
        findings: list[AuditFinding] = []
        if not REGISTER_PATH.exists():
            findings.append(self._finding("register_exists", "FAIL", f"Register not found: {REGISTER_PATH}"))
            return findings

        findings.append(self._finding("register_exists", "PASS", "compliance/register.yaml present"))

        try:
            with open(REGISTER_PATH) as f:
                register = yaml.safe_load(f)
        except Exception as e:
            findings.append(self._finding("register_parse", "FAIL", f"Cannot parse register: {e}"))
            return findings

        requirements = register.get("requirements", [])
        missing_evidence = []
        for req in requirements:
            req_id = req.get("id", "?")
            for ev in req.get("evidence", []):
                path = REPO_ROOT / ev
                if not path.exists():
                    missing_evidence.append(f"{req_id}: {ev}")

        if missing_evidence:
            findings.append(self._finding(
                "evidence_paths", "WARN",
                f"{len(missing_evidence)} evidence paths missing: {missing_evidence[:5]}..."
            ))
        else:
            findings.append(self._finding("evidence_paths", "PASS", f"All evidence paths present for {len(requirements)} requirements"))

        return findings

    # ── MC Rules Audit ────────────────────────────────────────────────────────

    def audit_mc_rules(self) -> list[AuditFinding]:
        """Run MC validator and report results."""
        findings: list[AuditFinding] = []
        try:
            sys.path.insert(0, str(REPO_ROOT))
            from src.compliance.mc_validator import run_all_validators, write_results
            results = run_all_validators()
            write_results(results)
            passed = sum(1 for r in results if r["passed"])
            total = len(results)
            status = "PASS" if passed == total else ("WARN" if passed >= total * 0.7 else "FAIL")
            findings.append(self._finding(
                "mc_rules", status,
                f"MC rules: {passed}/{total} passed"
            ))
            for r in results:
                if not r["passed"]:
                    findings.append(self._finding(f"mc_{r['rule_id']}", "FAIL", r["details"]))
        except Exception as e:
            findings.append(self._finding("mc_rules", "WARN", f"MC validator error: {e}"))
        return findings

    # ── Security Posture Audit ────────────────────────────────────────────────

    def audit_security_posture(self) -> list[AuditFinding]:
        """Check security controls are in place."""
        findings: list[AuditFinding] = []

        # Check SECRET_KEY is set and not default
        secret_key = os.getenv("SECRET_KEY", "")
        if not secret_key:
            findings.append(self._finding("secret_key", "FAIL", "SECRET_KEY not set"))
        elif secret_key in ("changeme", "secret", "development", "test"):
            findings.append(self._finding("secret_key", "FAIL", "SECRET_KEY is a weak default value"))
        else:
            findings.append(self._finding("secret_key", "PASS", "SECRET_KEY is set"))

        # Check JWT secret
        jwt_secret = os.getenv("JWT_SECRET", "")
        if not jwt_secret:
            findings.append(self._finding("jwt_secret", "WARN", "JWT_SECRET not set — JWT rotation may not function"))
        else:
            findings.append(self._finding("jwt_secret", "PASS", "JWT_SECRET is set"))

        # Check vault service
        vault_url = os.getenv("VAULT_SERVICE_URL", "")
        findings.append(self._finding(
            "vault_configured", "PASS" if vault_url else "WARN",
            f"Vault URL: {'configured' if vault_url else 'not configured — secrets from env only'}"
        ))

        # Check log redactor installed
        import logging as _logging
        root = _logging.getLogger()
        has_redactor = any("RedactingFilter" in type(f).__name__ for f in root.filters)
        findings.append(self._finding(
            "log_redactor", "PASS" if has_redactor else "WARN",
            "Log redactor: installed" if has_redactor else "Log redactor not installed (call install_global_redactor())"
        ))

        # Check critical security files exist
        security_files = [
            ("src/security/vault_client.py", "vault_client"),
            ("src/security/jwt_rotator.py", "jwt_rotator"),
            ("src/security/log_redactor.py", "log_redactor"),
            ("src/security/hipaa_sentinel.py", "hipaa_sentinel"),
            ("src/security/container_sentinel.py", "container_sentinel"),
            ("src/security/adaptive_rate_limiter.py", "adaptive_rate_limiter"),
        ]
        for rel_path, name in security_files:
            p = REPO_ROOT / rel_path
            status = "PASS" if p.exists() else "FAIL"
            findings.append(self._finding(f"file_{name}", status, f"{rel_path}: {'present' if p.exists() else 'MISSING'}"))

        return findings

    # ── Backup Audit ──────────────────────────────────────────────────────────

    def audit_backups(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        backup_dir = Path("./backups/sqlite")
        if backup_dir.exists():
            backups = list(backup_dir.rglob("*.db"))
            findings.append(self._finding("sqlite_backups", "PASS", f"{len(backups)} backup files found"))
        else:
            findings.append(self._finding(
                "sqlite_backups", "WARN",
                "No backup directory found — trigger backup_all() to initialise"
            ))
        return findings

    # ── DSR SLA Audit ────────────────────────────────────────────────────────

    def audit_dsr_sla(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        try:
            from src.privacy.dsr_workflow import get_workflow
            wf = get_workflow()
            report = wf.sla_report()
            if report["breached"] > 0:
                findings.append(self._finding(
                    "dsr_sla", "FAIL",
                    f"{report['breached']} DSR requests in SLA breach"
                ))
            elif report["high_risk"] > 0:
                findings.append(self._finding(
                    "dsr_sla", "WARN",
                    f"{report['high_risk']} DSR requests at high SLA risk"
                ))
            else:
                findings.append(self._finding("dsr_sla", "PASS", f"{report['active_requests']} active DSRs, all within SLA"))
        except Exception as e:
            findings.append(self._finding("dsr_sla", "WARN", f"DSR audit error: {e}"))
        return findings

    # ── Auto-remediation ──────────────────────────────────────────────────────

    async def auto_remediate(self, findings: list[AuditFinding]) -> list[str]:
        """Attempt to auto-remediate WARN/FAIL findings where possible."""
        actions: list[str] = []

        fail_checks = {f.check for f in findings if f.status in ("WARN", "FAIL")}

        # Trigger backup if not found
        if "sqlite_backups" in fail_checks:
            try:
                from src.database.sqlite_backup import backup_all
                results = backup_all()
                actions.append(f"Triggered SQLite backup: {len(results)} databases")
            except Exception as e:
                actions.append(f"Backup trigger failed: {e}")

        # Trigger JWT rotation if needed
        if "jwt_rotator" in fail_checks:
            try:
                from src.security.jwt_rotator import get_rotator
                rotator = get_rotator()
                if rotator.should_rotate():
                    rotator.rotate()
                    actions.append("JWT secret rotated")
            except Exception as e:
                actions.append(f"JWT rotation failed: {e}")

        # Re-run MC validators to generate fresh evidence
        if "mc_rules" in fail_checks:
            try:
                from src.compliance.mc_validator import main as mc_main
                mc_main()
                actions.append("MC validation re-run, evidence updated")
            except Exception as e:
                actions.append(f"MC validation failed: {e}")

        return actions

    # ── Main audit run ────────────────────────────────────────────────────────

    async def run(self) -> dict[str, Any]:
        self._findings.clear()
        logger.info("Starting automated compliance audit")

        self.audit_register_evidence()
        self.audit_mc_rules()
        self.audit_security_posture()
        self.audit_backups()
        self.audit_dsr_sla()

        remediation_actions = await self.auto_remediate(self._findings)

        passed = sum(1 for f in self._findings if f.status == "PASS")
        warned = sum(1 for f in self._findings if f.status == "WARN")
        failed = sum(1 for f in self._findings if f.status == "FAIL")
        total = len(self._findings)

        result = {
            "meta": {
                "audited_at": datetime.now(timezone.utc).isoformat(),
                "total_checks": total,
                "passed": passed,
                "warned": warned,
                "failed": failed,
                "score_pct": round(passed / total * 100, 1) if total else 0,
                "remediation_actions": remediation_actions,
            },
            "findings": [f.to_dict() for f in self._findings],
        }

        AUDIT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        AUDIT_OUTPUT.write_text(yaml.dump(result, default_flow_style=False, sort_keys=False))
        logger.info("Audit complete: %d/%d checks passed (%.1f%%)", passed, total, result["meta"]["score_pct"])
        return result

    async def audit_loop(self) -> None:
        """Background loop: run audit every AUDIT_INTERVAL_HOURS."""
        logger.info("Automated auditor started (interval: %dh)", AUDIT_INTERVAL_HOURS)
        while True:
            try:
                await self.run()
            except Exception as e:
                logger.error("Audit loop error: %s", e)
            await asyncio.sleep(AUDIT_INTERVAL_HOURS * 3600)


_auditor: AutomatedAuditor | None = None


def get_auditor() -> AutomatedAuditor:
    global _auditor
    if _auditor is None:
        _auditor = AutomatedAuditor()
    return _auditor
