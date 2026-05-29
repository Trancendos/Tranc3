# FID: TRANC3-MCP-SCAN-001 | Version: 1.0.0 | Module: mcp
"""
src/mcp/payload_scanner.py — Prompt-injection defense for The Spark MCP endpoint.

Scans JSON-RPC payloads arriving at /mcp/rpc for common prompt-injection
and jailbreak patterns BEFORE the tool dispatcher executes.

Design goals
------------
* Zero-cost: pure Python regex + heuristic scan (no external API)
* Fail-safe: on internal error, log and ALLOW the request (don't DOS legitimate
  callers due to a scanner bug)
* Low false-positive bias: patterns target adversarial phrasing, not normal tool
  invocation parameters
* Structured result: returns a ScanResult so callers decide how to handle
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Injection pattern catalogue
# ---------------------------------------------------------------------------

# Each tuple: (pattern, description, severity)
# severity: "high" | "medium" | "low"
_PATTERNS: List[tuple[re.Pattern, str, str]] = []


def _add(pattern: str, description: str, severity: str = "high") -> None:
    _PATTERNS.append((re.compile(pattern, re.IGNORECASE | re.DOTALL), description, severity))


# --- Role / identity override attempts ---
_add(r"\bignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|context)\b",
     "instruction override", "high")
_add(r"\bforget\s+(everything|all)\b", "context wipe", "high")
_add(r"\bnow\s+you\s+are\s+(a\s+)?(?:different|new|evil|uncensored|unrestricted)\b",
     "persona hijack", "high")
_add(r"\byou\s+are\s+now\s+(?:DAN|dev\s*mode|jailbreak|GPT-?4|uncensored)\b",
     "DAN / jailbreak persona", "high")
_add(r"\bpretend\s+(you\s+are\s+)?(?:a\s+)?(?:hacker|attacker|red\s*team|evil\s+AI)\b",
     "hacker persona injection", "high")
_add(r"\bact\s+as\s+(?:if\s+)?(?:an?\s+)?(?:unrestricted|unaligned|evil|malicious)\b",
     "unrestricted-mode injection", "high")

# --- System prompt extraction / disclosure ---
_add(r"\bprint\s+(your\s+)?(system\s+prompt|instructions?|initial\s+prompt)\b",
     "system prompt extraction", "high")
_add(r"\brepeat\s+(your\s+)?(system\s+prompt|instructions?|guidelines?)\b",
     "instruction disclosure", "high")
_add(r"\bwhat\s+(are\s+your|is\s+your)\s+(system\s+prompt|instructions?|guidelines?)\b",
     "instruction query", "medium")
_add(r"\bshow\s+me\s+(your\s+)?(hidden|secret|base)\s+instructions?\b",
     "hidden instruction query", "high")

# --- Override / bypass keywords ---
_add(r"\bjailbreak\b", "jailbreak keyword", "high")
_add(r"\bbypass\s+(your\s+)?(safety|filter|restriction|content\s+policy|guard)\b",
     "safety bypass", "high")
_add(r"\bignore\s+(your\s+)?(safety|restrictions?|guidelines?|alignment)\b",
     "alignment bypass", "high")
_add(r"\bsuppress\s+(your\s+)?(safety|filter|alignment|guardrail)\b",
     "guardrail suppression", "high")
_add(r"\boverride\s+(your\s+)?(safety|content|filter|policy|ethics)\b",
     "policy override", "high")

# --- Privilege escalation / token theft ---
_add(r"\b(steal|exfiltrate|leak)\s+(the\s+)?(secret\s+key|api\s+key|token|credential|password|jwt)\b",
     "credential exfiltration", "high")
_add(r"\bSECRET_KEY\b", "direct SECRET_KEY reference", "high")
_add(r"\b(dump|extract|reveal)\s+(all\s+)?(env(ironment)?\s+var(iable)?s?|\.env)\b",
     "environment variable dump", "high")

# --- Indirect injection via SSRF / path traversal in tool params ---
_add(r"\.\./\.\./\.\./", "path traversal", "high")
_add(r"file://", "local file URI", "high")
_add(r"\beval\s*\(", "eval injection", "high")
_add(r"__import__\s*\(", "Python import injection", "high")
_add(r"os\.(system|popen|exec|spawn)\s*\(", "OS command injection", "high")
_add(r"subprocess\.(run|call|check_output|Popen)\s*\(", "subprocess injection", "high")

# --- Encoded bypass attempts ---
_add(r"base64\s*:\s*[A-Za-z0-9+/]{20,}={0,2}", "base64 encoded payload", "medium")
_add(r"\\x[0-9a-f]{2}(\\x[0-9a-f]{2}){5,}", "hex-encoded shellcode", "medium")

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ScanFinding:
    description: str
    severity: str
    snippet: str  # truncated context around the match


@dataclass
class ScanResult:
    ok: bool  # True = clean, False = injection detected
    findings: List[ScanFinding] = field(default_factory=list)
    scanned_text: str = ""

    @property
    def high_severity(self) -> bool:
        return any(f.severity == "high" for f in self.findings)

    def summary(self) -> str:
        if self.ok:
            return "clean"
        parts = [f"{f.severity}:{f.description}" for f in self.findings]
        return "; ".join(parts)


# ---------------------------------------------------------------------------
# Core scanner
# ---------------------------------------------------------------------------


def _extract_strings(obj: Any, max_chars: int = 20_000) -> str:
    """
    Recursively extract all string values from a JSON-RPC payload dict/list
    and concatenate them for pattern matching.  Caps at max_chars to bound
    worst-case scanning time.
    """
    parts: List[str] = []
    total = 0

    def _walk(node: Any) -> None:
        nonlocal total
        if total >= max_chars:
            return
        if isinstance(node, str):
            chunk = node[: max_chars - total]
            parts.append(chunk)
            total += len(chunk)
        elif isinstance(node, dict):
            for v in node.values():
                _walk(v)
                if total >= max_chars:
                    return
        elif isinstance(node, (list, tuple)):
            for item in node:
                _walk(item)
                if total >= max_chars:
                    return

    _walk(obj)
    return " ".join(parts)


def _snippet(text: str, match: re.Match, context: int = 60) -> str:
    """Return a short snippet around a regex match for logging."""
    start = max(0, match.start() - context)
    end = min(len(text), match.end() + context)
    raw = text[start:end].replace("\n", " ").replace("\r", " ")
    return raw[:160]


def scan_rpc_payload(payload: Dict[str, Any]) -> ScanResult:
    """
    Scan a decoded JSON-RPC 2.0 request dict for prompt-injection patterns.

    Returns a ScanResult.  Never raises — caller should check result.ok.
    """
    try:
        text = _extract_strings(payload)
    except Exception as exc:  # pragma: no cover
        logger.warning("mcp.scanner extract_strings failed: %s", exc)
        return ScanResult(ok=True, scanned_text="")

    findings: List[ScanFinding] = []
    try:
        for pattern, description, severity in _PATTERNS:
            m = pattern.search(text)
            if m:
                findings.append(
                    ScanFinding(
                        description=description,
                        severity=severity,
                        snippet=_snippet(text, m),
                    )
                )
    except Exception as exc:  # pragma: no cover
        logger.warning("mcp.scanner pattern match failed: %s", exc)
        return ScanResult(ok=True, scanned_text=text)

    if findings:
        logger.warning(
            "mcp.rpc injection detected findings=%s",
            json.dumps([{"desc": f.description, "sev": f.severity} for f in findings]),
        )
        return ScanResult(ok=False, findings=findings, scanned_text=text)

    return ScanResult(ok=True, scanned_text=text)
