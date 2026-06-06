"""Human-readable catalog for all security rules detected by SecurityScanner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class RuleInfo:
    rule_id: str
    name: str
    description: str
    what_it_means: str
    remediation: str
    severity: str  # "critical" | "high" | "medium" | "low"
    cwe_url: str
    auto_fixable: bool
    fix_notes: str = ""
    tags: List[str] = field(default_factory=list)


RULE_CATALOG: Dict[str, RuleInfo] = {
    "CWE-022": RuleInfo(
        rule_id="CWE-022",
        name="Path Traversal",
        description="User-controlled data used in file path without sanitisation.",
        what_it_means="An attacker can escape the intended directory by injecting '../' sequences, potentially reading /etc/passwd or overwriting system files.",
        remediation="Wrap every open() call that uses user input with validate_path(path, base_dir). The AutoRemediatorV2 can insert this guard automatically.",
        severity="high",
        cwe_url="https://cwe.mitre.org/data/definitions/22.html",
        auto_fixable=True,
        fix_notes="remediator_v2.FixPathTraversal inserts validate_path() guard before open() calls.",
        tags=["filesystem", "injection"],
    ),
    "CWE-117": RuleInfo(
        rule_id="CWE-117",
        name="Log Injection",
        description="User-supplied data written into log output using f-strings.",
        what_it_means="An attacker can inject newlines into logs to forge log entries, hide malicious activity, or corrupt log aggregation (Loki/Splunk). With 9,021 observed instances this is the highest-volume issue in the codebase.",
        remediation="Convert logger.info(f'...{var}...') to logger.info('...%s...', sanitize_for_log(var)). The AutoRemediator handles this automatically.",
        severity="medium",
        cwe_url="https://cwe.mitre.org/data/definitions/117.html",
        auto_fixable=True,
        fix_notes="remediator._fix_log_injection converts f-string loggers to %-style with sanitize_for_log().",
        tags=["logging", "injection"],
    ),
    "CWE-209": RuleInfo(
        rule_id="CWE-209",
        name="Information Exposure Through Error Messages",
        description="Exception detail (str(exc)) returned directly in HTTP error responses.",
        what_it_means="Stack traces, database queries, or internal paths leak to API clients, giving attackers a roadmap to the system internals.",
        remediation="Replace detail=str(exc) with detail=safe_error_detail(exc, status_code). AutoRemediatorV2 handles this.",
        severity="medium",
        cwe_url="https://cwe.mitre.org/data/definitions/209.html",
        auto_fixable=True,
        fix_notes="remediator_v2.FixInfoExposure replaces str(exc) in HTTP error details.",
        tags=["error-handling", "api"],
    ),
    "CWE-327": RuleInfo(
        rule_id="CWE-327",
        name="Use of Broken or Risky Cryptographic Algorithm",
        description="MD5 or SHA-1 used without usedforsecurity=False.",
        what_it_means="MD5 and SHA-1 are cryptographically broken. Without usedforsecurity=False, static analysis tools flag these as active security risks even when used for non-security purposes (e.g. content hashing).",
        remediation="Add usedforsecurity=False to hashlib.md5() and hashlib.sha1() calls, or migrate to SHA-256/SHA-3 for any security purpose.",
        severity="low",
        cwe_url="https://cwe.mitre.org/data/definitions/327.html",
        auto_fixable=True,
        fix_notes="remediator_v2.FixWeakHash adds usedforsecurity=False parameter.",
        tags=["cryptography"],
    ),
    "CWE-605": RuleInfo(
        rule_id="CWE-605",
        name="Multiple Binds to Same Port",
        description="Socket bound to a port without SO_REUSEADDR/SO_REUSEPORT.",
        what_it_means="Without address reuse flags, server restarts will fail with 'Address already in use' — causing downtime in Docker/container environments where ports linger after process exit.",
        remediation="Add sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) before bind(), or use framework-level server configuration.",
        severity="low",
        cwe_url="https://cwe.mitre.org/data/definitions/605.html",
        auto_fixable=False,
        tags=["networking", "availability"],
    ),
    "PY-001": RuleInfo(
        rule_id="PY-001",
        name="Bare Except Clause",
        description="except: without specifying exception type.",
        what_it_means="Bare except catches SystemExit, KeyboardInterrupt, and GeneratorExit — Python signals that should not be swallowed. This masks crashes and makes debugging impossible.",
        remediation="Replace except: with except Exception: to avoid catching system signals. AutoRemediator handles this.",
        severity="low",
        cwe_url="",
        auto_fixable=True,
        fix_notes="remediator._fix_bare_except replaces bare except: with except Exception:.",
        tags=["error-handling", "python"],
    ),
    "PY-008": RuleInfo(
        rule_id="PY-008",
        name="Mixed Explicit and Implicit Return",
        description="Function has both return <value> and implicit return None paths.",
        what_it_means="A function that sometimes returns a value and sometimes falls off the end returns None unpredictably. Callers that expect a value get None silently. With 10,861 observed instances this is the highest-volume issue by count.",
        remediation="Add explicit return None at the end of functions that have explicit return <value> paths. AutoRemediatorV2 handles this using AST analysis.",
        severity="low",
        cwe_url="",
        auto_fixable=True,
        fix_notes="remediator_v2.FixMixedReturn inserts return None using AST-safe transformation.",
        tags=["python", "code-quality"],
    ),
    "PY-009": RuleInfo(
        rule_id="PY-009",
        name="Mutable Default Argument",
        description="Function uses mutable object (list/dict/set) as default argument.",
        what_it_means="Python creates default argument objects once at function definition time. Mutating a default list/dict persists across calls — a notorious source of state-leaking bugs.",
        remediation="Replace def f(x=[]) with def f(x=None) and set x = x if x is not None else [] inside the function.",
        severity="low",
        cwe_url="",
        auto_fixable=False,
        tags=["python", "code-quality"],
    ),
}


# ---------------------------------------------------------------------------
# Entity map — maps directory prefix → Trancendos platform entity name
# ---------------------------------------------------------------------------

ENTITY_MAP: Dict[str, str] = {
    "src/mcp": "The Spark",
    "src/workflow": "The Digital Grid",
    "src/auth": "Infinity (Core Auth)",
    "src/ai_gateway": "Luminous (AI Gateway)",
    "src/bio_neural": "Luminous",
    "src/core": "Luminous (Core)",
    "src/personality": "Turing's Hub",
    "src/event_bus": "The Digital Grid (Event Bus)",
    "src/mesh": "The Digital Grid (Service Mesh)",
    "src/observability": "The Observatory",
    "src/security": "Cryptex",
    "src/quantum": "Think Tank",
    "src/deepmind": "Think Tank",
    "src/monetisation": "Royal Bank of Arcadia",
    "src/database": "Arcadia (Data Layer)",
    "src/knowledge": "The Spark (RAG)",
    "src/registry": "The Spark (Registry)",
    "src/nanoservices": "The HIVE (Nanoservices)",
    "src/townhall": "The Town Hall",
    "src/workers": "The HIVE (Workers)",
    "src/validation": "Cryptex (Validation)",
    "src/errors": "The Observatory (Errors)",
    "workers/infinity-ws": "The Nexus",
    "workers/infinity-auth": "Infinity",
    "workers/hive-service": "The HIVE",
    "workers/infinity-ai": "Luminous (AI Worker)",
    "workers/monitoring": "The Observatory",
    "workers/gateway-service": "API Gateway",
    "workers/sentinel-station-service": "Cryptex (Sentinel)",
    "workers/vault-service": "The Void",
    "cloudflare": "Cloudflare (Legacy)",
    "tests": "The Chaos Party",
    "tranc3-bots": "The HIVE (Bots)",
    "shared_core": "Platform Core",
    "web": "Arcadia (Frontend)",
    "scripts": "The Citadel (Scripts)",
    "deploy": "The Citadel",
    "monitoring": "The Observatory (Monitoring)",
}


def entity_for_directory(directory: str) -> str:
    """Return the Trancendos platform entity that owns a directory.

    Tries progressively shorter path prefixes until a match is found.
    Falls back to 'Unknown' if no match.
    """
    directory = directory.replace("\\", "/").rstrip("/")
    # Try longest match first
    for prefix_len in range(len(directory.split("/")), 0, -1):
        candidate = "/".join(directory.split("/")[:prefix_len])
        if candidate in ENTITY_MAP:
            return ENTITY_MAP[candidate]
    return "Unknown"


def rule_info(rule_id: str) -> Optional[RuleInfo]:
    """Return rule info for a rule_id, or None if unknown."""
    return RULE_CATALOG.get(rule_id)
