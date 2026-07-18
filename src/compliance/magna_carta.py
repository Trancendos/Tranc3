# src/compliance/magna_carta.py
# TRANC3 Magna Carta Framework Compliance Layer
# Full rule engine — MC-RULE-001 through MC-RULE-009

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger("tranc3.compliance.magna_carta")

MAGNA_CARTA_ENABLED = os.getenv("MAGNA_CARTA_ENABLED", "false").lower() == "true"
MAGNA_CARTA_CONFIG_PATH = os.getenv(
    "MAGNA_CARTA_CONFIG_PATH",
    "./compliance/magna-carta/config/magna_carta_config.json",
)
MAGNA_CARTA_REGISTER_PATH = os.getenv("MAGNA_CARTA_REGISTER_PATH", "")
MAGNA_CARTA_AUDIT = os.getenv("MAGNA_CARTA_AUDIT", "true").lower() == "true"

# Paid API patterns blocked under zero-cost sovereignty (MC-RULE-005)
_PAID_API_PATTERNS = [
    r"openai\.com",
    r"api\.anthropic\.com",
    r"cohere\.ai",
    r"pinecone\.io",
    r"stripe\.com/v1",
    r"twilio\.com",
    r"sendgrid\.com",
    r"google\.com/maps",
    r"mapbox\.com",
]

# PII field names that must never appear in logs or unguarded responses (MC-RULE-002)
_PII_FIELDS = {
    "password",
    "ssn",
    "credit_card",
    "api_key",
    "refresh_token",
    "phi",
    "medical_record_number",
    "health_plan_id",
    "secret",
    "private_key",
    "card_number",
    "cvv",
    "date_of_birth",
    "national_insurance",
}

# High-risk change types requiring CAB approval (MC-RULE-007)
_HIGH_RISK_CHANGES = {
    "auth_model_change",
    "encryption_key_rotation",
    "data_retention_change",
    "ai_model_deployment",
    "supplier_onboarding",
}

# Prohibited AI uses (MC-RULE-004)
_PROHIBITED_AI_USES = {
    "social_scoring",
    "real_time_biometric_identification_public",
    "manipulative_subliminal_techniques",
    "unauthorised_law_enforcement_profiling",
    "subliminal manipulation",
    "mass surveillance",
}

# AI routes that require governance (MC-RULE-004)
_AI_ROUTE_PREFIXES = ("/ai/", "/infinity-ai/", "/model-router/")

# Protected routes requiring auth (MC-RULE-001)
_PROTECTED_PREFIXES = (
    "/api/",
    "/townhall/",
    "/vault/",
    "/chat",
    "/billing/",
    "/feedback",
    "/consciousness/",
    "/admin/",
    "/memory/",
    "/mcp/",
    "/workflow/",
)
_EXCLUDED_PATHS = {"/health", "/metrics", "/docs", "/openapi.json", "/favicon.ico"}


class MagnaCartaCompliance:
    """
    Full Magna Carta runtime compliance engine.

    Rules MC-RULE-001 through MC-RULE-009 are fully implemented.
    enforcement.fail_closed_on_violation is respected from config.
    When MAGNA_CARTA_ENABLED=false all checks return compliant=True (advisory off).
    """

    def __init__(self) -> None:
        self.enabled = MAGNA_CARTA_ENABLED
        self.config: Optional[Dict[str, Any]] = self._load_config()
        self._profiles: Dict[str, str] = {}
        self._enforcement: Dict[str, Any] = {}
        if self.config:
            self._profiles = self.config.get("profiles", {})
            self._enforcement = self.config.get("enforcement", {})
        if self.enabled:
            logger.info(
                "Magna Carta compliance framework ACTIVE — %d rules loaded, mode=%s",
                len(self.config.get("rules", [])) if self.config else 0,
                self._enforcement.get("mode", "advisory"),
            )
        else:
            logger.info(
                "Magna Carta compliance framework INACTIVE — set MAGNA_CARTA_ENABLED=true to activate"
            )

    # ── Config loading ────────────────────────────────────────────────────────

    def _load_config(self) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        import json

        path = MAGNA_CARTA_CONFIG_PATH
        try:
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
            logger.info("Magna Carta config loaded from %s", sanitize_for_log(path))
            return cfg
        except FileNotFoundError:
            logger.warning(
                "Magna Carta config not found at %s — framework will operate in advisory-pass mode",
                sanitize_for_log(path),
            )
            return None
        except Exception as exc:
            logger.error("Magna Carta config load error: %s", sanitize_for_log(exc))
            return None

    # ── Public API ─────────────────────────────────────────────────────────────

    def check_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate a request against all enabled Magna Carta rules.

        request_data keys (all optional):
          path           str   — URL path being accessed
          method         str   — HTTP method
          headers        dict  — request headers
          user_id        str   — authenticated user identity
          jwt_claims     dict  — decoded JWT claims
          zero_trust_ok  bool  — result of Zero Trust posture check
          body_keys      list  — top-level keys present in request body
          tenant_tier    str   — "free" | "pro" | "business"
          request_count  int   — requests made by tenant this hour
          ip             str   — source IP
          model_id       str   — AI model being invoked (AI routes)
          use_case       str   — stated purpose (AI routes)
          change_type    str   — type of platform change (governance routes)
          cab_approved   bool  — CAB approval status
          response_body  dict  — outgoing response (for response checks)
          external_url   str   — URL being called by this request (zero-cost)
        """
        if not self.enabled or not self.config:
            return {"compliant": True, "violations": [], "framework": "inactive"}

        violations: List[Dict[str, Any]] = []
        rules = self.config.get("rules", [])

        for rule in rules:
            if not rule.get("enabled", True):
                continue
            result = self._apply_rule(rule, request_data)
            if not result["passed"]:
                violations.append(result)
                if (
                    self._enforcement.get("fail_closed_on_violation")
                    and result.get("severity") == "high"
                ):
                    break  # stop on first high-severity breach in strict mode

        outcome = {
            "compliant": len(violations) == 0,
            "violations": violations,
            "framework": "magna_carta_v1",
            "rules_checked": len(rules),
            "mode": self._enforcement.get("mode", "advisory"),
            "fail_closed": bool(self._enforcement.get("fail_closed_on_violation", False)),
        }

        if MAGNA_CARTA_AUDIT:
            self.audit_log(
                "check_request",
                {
                    "path": request_data.get("path"),
                    "compliant": outcome["compliant"],
                    "violation_count": len(violations),
                },
            )
        return outcome

    def check_response(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Lightweight response-side checks (PII scrubbing, AI disclosure).
        Delegates to MC-RULE-002 and MC-RULE-008 only.
        """
        if not self.enabled or not self.config:
            return {"compliant": True, "violations": [], "framework": "inactive"}

        violations: List[Dict[str, Any]] = []
        for rule in self.config.get("rules", []):
            if rule.get("id") in ("MC-RULE-002", "MC-RULE-008") and rule.get("enabled", True):
                result = self._apply_rule(rule, response_data)
                if not result["passed"]:
                    violations.append(result)

        return {
            "compliant": len(violations) == 0,
            "violations": violations,
            "framework": "magna_carta_v1",
        }

    def audit_log(self, event: str, data: Dict[str, Any]) -> None:
        if self.enabled and MAGNA_CARTA_AUDIT:
            logger.info(
                "MAGNA_CARTA_AUDIT | event=%s | data=%s",
                sanitize_for_log(event),
                sanitize_for_log(data),
            )

    # ── Rule dispatcher ───────────────────────────────────────────────────────

    def _apply_rule(self, rule: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        rule_id = rule.get("id", "unknown")
        rule_type = rule.get("type", "")
        severity = rule.get("severity", "medium")

        handlers = {
            "authentication": self._rule_authentication,
            "privacy": self._rule_privacy,
            "rate_limit": self._rule_rate_limit,
            "ai_governance": self._rule_ai_governance,
            "zero_cost": self._rule_zero_cost,
            "audit": self._rule_audit,
            "governance": self._rule_governance,
            "transparency": self._rule_transparency,
            "health_data": self._rule_health_data,
        }

        handler = handlers.get(rule_type)
        if handler is None:
            return {
                "rule_id": rule_id,
                "passed": True,
                "message": f"Unknown rule type '{rule_type}' — skipped",
            }

        try:
            passed, message, detail = handler(rule, data)
        except Exception as exc:
            logger.error(
                "Magna Carta rule %s raised exception: %s",
                rule_id,
                sanitize_for_log(exc),
            )
            # Fail safe: don't block on handler errors unless fail-closed
            passed = not self._enforcement.get("fail_closed_on_violation", False)
            message = f"Rule handler error ({rule_id})"
            detail = {}

        return {
            "rule_id": rule_id,
            "type": rule_type,
            "title": rule.get("title", ""),
            "severity": severity,
            "passed": passed,
            "message": message,
            **detail,
        }

    # ── Rule implementations ──────────────────────────────────────────────────

    def _rule_authentication(self, rule: Dict, data: Dict) -> tuple[bool, str, Dict]:
        """MC-RULE-001: JWT + Zero Trust check on protected paths."""
        path = data.get("path", "")

        # Excluded paths always pass
        if path in _EXCLUDED_PATHS or not any(path.startswith(p) for p in _PROTECTED_PREFIXES):
            return True, "Path not in protected scope", {}

        # Check scope exclusions from config
        scope = rule.get("scope") or {}
        for excl in scope.get("exclude_paths") or []:
            excl_norm = excl.rstrip("*")
            if path.startswith(excl_norm) or path == excl_norm.rstrip("/"):
                return True, "Path excluded from rule scope", {}

        checks = rule.get("checks") or []
        failures = []

        if "jwt_present" in checks:
            headers = data.get("headers") or {}
            auth = headers.get("authorization") or headers.get("Authorization") or ""
            if not isinstance(auth, str) or not auth.startswith("Bearer "):
                failures.append("jwt_present")

        if "jwt_not_expired" in checks:
            claims = data.get("jwt_claims") or {}
            import time

            exp = claims.get("exp")
            if exp is None or int(exp) < int(time.time()):
                failures.append("jwt_not_expired")

        if "zero_trust_passed" in checks:
            if data.get("zero_trust_ok") is not True:
                failures.append("zero_trust_passed")

        if failures:
            return (
                False,
                f"Authentication checks failed: {', '.join(failures)}",
                {"failed_checks": failures},
            )
        return True, "Authentication checks passed", {}

    def _rule_privacy(self, rule: Dict, data: Dict) -> tuple[bool, str, Dict]:
        """MC-RULE-002: PII/sensitive field detection in body and logs."""
        blocked = set(rule.get("blocked_fields", [])) | _PII_FIELDS
        failures = []

        # Check body keys
        for key in data.get("body_keys", []):
            if key.lower() in blocked:
                failures.append(f"body_field:{key}")

        # Check response body keys too
        for key in (data.get("response_body") or {}).keys():
            if key.lower() in blocked:
                failures.append(f"response_field:{key}")

        # Check for raw PII patterns in any string value provided
        for field_val in [data.get("raw_body", ""), data.get("log_fragment", "")]:
            if not isinstance(field_val, str):
                continue
            for pat in _PII_FIELDS:
                if re.search(rf"\b{pat}\b", field_val, re.IGNORECASE):
                    failures.append(f"raw_pattern:{pat}")
                    break

        if failures:
            return (
                False,
                f"PII/sensitive data exposure: {', '.join(failures[:5])}",
                {"failed_checks": failures},
            )
        return True, "Privacy checks passed", {}

    def _rule_rate_limit(self, rule: Dict, data: Dict) -> tuple[bool, str, Dict]:
        """MC-RULE-003: Tier-based rate limit enforcement."""
        tiers = rule.get("tiers", {})
        tenant_tier = data.get("tenant_tier", "free")
        request_count = data.get("request_count")

        if request_count is None:
            # No count provided — advisory pass
            return True, "Rate limit advisory (no count provided)", {}

        tier_config = tiers.get(tenant_tier, tiers.get("free", {}))
        limit = tier_config.get("requests_per_hour", 100)

        if request_count > limit:
            return (
                False,
                (f"Rate limit exceeded: {request_count}/{limit} req/hr for tier '{tenant_tier}'"),
                {"limit": limit, "count": request_count, "tier": tenant_tier},
            )

        return True, f"Rate limit OK ({request_count}/{limit})", {}

    def _rule_ai_governance(self, rule: Dict, data: Dict) -> tuple[bool, str, Dict]:
        """MC-RULE-004: AI model registration, risk tier, prohibited-use checks."""
        path = data.get("path", "")

        # Only applies to AI-scope paths
        if not any(path.startswith(p) for p in _AI_ROUTE_PREFIXES):
            return True, "Not an AI route — rule skipped", {}

        checks = rule.get("checks", [])
        failures = []
        from src.compliance.ai_governance import MODEL_REGISTRY, classify_risk

        model_id = data.get("model_id", "")
        use_case = data.get("use_case", "")

        if "model_registered" in checks:
            if model_id and model_id not in MODEL_REGISTRY:
                failures.append(f"model_not_registered:{model_id}")

        if "risk_tier_documented" in checks and model_id:
            classification = classify_risk(model_id, use_case)
            if classification["risk_tier"] == "unacceptable":
                failures.append(f"unacceptable_risk_tier:{model_id}")

        if "prohibited_use_blocked" in checks:
            use_lower = use_case.lower()
            for prohibited in set(rule.get("prohibited_uses") or []) | _PROHIBITED_AI_USES:
                if prohibited.replace("_", " ") in use_lower or prohibited in use_lower:
                    failures.append(f"prohibited_use:{prohibited}")

        if "human_review_required_for_high_risk" in checks and model_id:
            classification = classify_risk(model_id, use_case)
            if classification["risk_tier"] == "high" and not data.get("human_review_approved"):
                failures.append("high_risk_no_human_review")

        if failures:
            return (
                False,
                f"AI governance violations: {', '.join(failures)}",
                {
                    "failed_checks": failures,
                    "model_id": model_id,
                },
            )
        return True, "AI governance checks passed", {}

    def _rule_zero_cost(self, rule: Dict, data: Dict) -> tuple[bool, str, Dict]:
        """MC-RULE-005: Paid API dependency block."""
        checks = rule.get("checks", [])
        failures = []
        external_url = data.get("external_url", "")

        if "no_mandatory_paid_api" in checks and external_url:
            # Check exceptions
            exceptions = rule.get("allowed_exceptions", [])
            for pattern in _PAID_API_PATTERNS:
                if re.search(pattern, external_url):
                    # Allowed if exception flag is set in request data
                    allowed = any(data.get(exc) for exc in exceptions)
                    if not allowed:
                        failures.append(f"paid_api:{pattern}")

        if "vendor_lock_in_assessed" in checks:
            if data.get("vendor_lock_in_assessed") is False:
                failures.append("vendor_lock_in_not_assessed")

        if failures:
            return (
                False,
                f"Zero-cost sovereignty violations: {', '.join(failures)}",
                {"failed_checks": failures},
            )
        return True, "Zero-cost sovereignty checks passed", {}

    def _rule_audit(self, rule: Dict, data: Dict) -> tuple[bool, str, Dict]:
        """MC-RULE-006: Structured audit event completeness."""
        checks = rule.get("checks", [])
        failures = []

        audit_event = data.get("audit_event", {})
        if not audit_event:
            # Not an audit event context — pass
            return True, "Not an audit event context", {}

        if "timestamp_present" in checks and not audit_event.get("timestamp"):
            failures.append("timestamp_missing")
        if "actor_identity_present" in checks and not audit_event.get("actor_id"):
            failures.append("actor_identity_missing")
        if "source_ip_present" in checks and not audit_event.get("source_ip"):
            failures.append("source_ip_missing")
        if "action_recorded" in checks and not audit_event.get("action"):
            failures.append("action_missing")

        if failures:
            return (
                False,
                f"Audit log completeness failures: {', '.join(failures)}",
                {"failed_checks": failures},
            )
        return True, "Audit event completeness checks passed", {}

    def _rule_governance(self, rule: Dict, data: Dict) -> tuple[bool, str, Dict]:
        """MC-RULE-007: Town Hall governance gate for material changes."""
        change_type = data.get("change_type", "")
        if not change_type:
            return True, "No change_type in request — governance gate skipped", {}

        checks = rule.get("checks", [])
        failures = []
        high_risk = set(rule.get("high_risk_change_types", [])) | _HIGH_RISK_CHANGES

        if "change_record_exists" in checks and not data.get("change_record_id"):
            failures.append("no_change_record")

        if "cab_approval_for_high_risk" in checks:
            if change_type in high_risk and not data.get("cab_approved"):
                failures.append(f"cab_approval_required_for:{change_type}")

        if "compliance_review_complete" in checks and not data.get("compliance_review_done"):
            if change_type in high_risk:
                failures.append("compliance_review_incomplete")

        if failures:
            return (
                False,
                f"Governance gate failures: {', '.join(failures)}",
                {
                    "failed_checks": failures,
                    "change_type": change_type,
                },
            )
        return True, "Governance gate passed", {}

    def _rule_transparency(self, rule: Dict, data: Dict) -> tuple[bool, str, Dict]:
        """MC-RULE-008: Digital rights transparency (GDPR Art. 13/14, EU AI Act Art. 50)."""
        checks = rule.get("checks", [])
        failures = []

        if "privacy_notice_linked" in checks:
            headers = data.get("headers", {})
            # Accept either a header or a flag in request data
            if not (
                headers.get("x-privacy-notice")
                or data.get("privacy_notice_linked")
                or data.get("path", "").startswith("/privacy")
            ):
                # Only flag on user-facing pages, not internal API calls
                if data.get("user_facing", False):
                    failures.append("privacy_notice_not_linked")

        if "ai_disclosure_when_applicable" in checks:
            if data.get("is_ai_response") and not data.get("ai_disclosed"):
                failures.append("ai_disclosure_missing")

        if "rights_contact_documented" in checks:
            if data.get("check_rights_contact") and not data.get("rights_contact_present"):
                failures.append("rights_contact_undocumented")

        if failures:
            return (
                False,
                f"Transparency obligations unmet: {', '.join(failures)}",
                {"failed_checks": failures},
            )
        return True, "Transparency checks passed", {}

    def _rule_health_data(self, rule: Dict, data: Dict) -> tuple[bool, str, Dict]:
        """MC-RULE-009: HIPAA/PHI boundary controls — gated by HIPAA_PROFILE=enabled."""
        # Only enforce when HIPAA profile is active
        if self._profiles.get("HIPAA_PROFILE", "disabled") != "enabled":
            return True, "HIPAA_PROFILE not enabled — health data rule skipped", {}

        path = data.get("path", "")
        scope_paths = rule.get("scope", {}).get("paths", ["/sync/", "/wellbeing/", "/health/"])
        if not any(path.startswith(p) for p in scope_paths):
            return True, "Path not in HIPAA scope", {}

        checks = rule.get("checks", [])
        failures = []

        if "baa_signed" in checks and not data.get("baa_signed"):
            failures.append("baa_not_signed")
        if "phi_encrypted_at_rest" in checks and not data.get("phi_encrypted_at_rest"):
            failures.append("phi_not_encrypted_at_rest")
        if "phi_encrypted_in_transit" in checks:
            scheme = data.get("scheme", "https")
            if scheme != "https":
                failures.append("phi_not_encrypted_in_transit")
        if "us_data_residency" in checks and not data.get("us_data_residency"):
            failures.append("us_data_residency_unconfirmed")
        if "phi_redacted_in_logs" in checks and not data.get("phi_redacted_in_logs"):
            failures.append("phi_not_redacted_in_logs")
        if "external_ai_on_phi_blocked" in checks:
            if data.get("external_ai_used_on_phi"):
                failures.append("external_ai_on_phi")
        if "marketing_claim_tier_valid" in checks:
            claim = data.get("marketing_claim_tier", "")
            valid_tiers = {"tier_a", "tier_b", "tier_c", ""}
            if claim not in valid_tiers:
                failures.append(f"invalid_marketing_claim_tier:{claim}")

        if failures:
            return (
                False,
                f"HIPAA/PHI boundary violations: {', '.join(failures)}",
                {"failed_checks": failures},
            )
        return True, "HIPAA health data checks passed", {}


# Singleton
compliance = MagnaCartaCompliance()
