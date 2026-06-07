"""
Ice Box — Threat Signature Library
====================================
YARA-style pattern rules for static threat detection, grouped by category.
All patterns are compiled once at import time.

Categories
----------
INJECTION       SQL, NoSQL, LDAP, XPath, command, template injection
XSS             Cross-site scripting payloads
PATH_TRAVERSAL  Directory traversal attempts
MALWARE         Shellcode stubs, reverse-shell patterns, crypto-miner markers
CREDENTIAL_LEAK API keys, private keys, JWT secrets in submitted content
EXFILTRATION    DNS-tunnelling, encoded C2 beacons
SUSPICIOUS_EXEC eval()/exec() abuse, subprocess with user input
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Pattern


class ThreatCategory(Enum):
    INJECTION = "injection"
    XSS = "xss"
    PATH_TRAVERSAL = "path_traversal"
    MALWARE = "malware"
    CREDENTIAL_LEAK = "credential_leak"
    EXFILTRATION = "exfiltration"
    SUSPICIOUS_EXEC = "suspicious_exec"
    BINARY_EXPLOIT = "binary_exploit"
    POLICY_VIOLATION = "policy_violation"


@dataclass
class Signature:
    id: str
    category: ThreatCategory
    severity: str  # critical | high | medium | low
    description: str
    pattern: Pattern
    false_positive_note: str = ""


def _c(pattern: str, flags: int = re.IGNORECASE | re.DOTALL) -> Pattern:
    return re.compile(pattern, flags)


# ---------------------------------------------------------------------------
# Signature definitions
# ---------------------------------------------------------------------------

_RAW: list[tuple] = [
    # ── INJECTION ──────────────────────────────────────────────────────────
    (
        "SIG-INJ-001",
        ThreatCategory.INJECTION,
        "critical",
        "SQL UNION-based injection",
        r"(?i)(?:union\s+(?:all\s+)?select|union\s+select\s+null)",
    ),
    (
        "SIG-INJ-002",
        ThreatCategory.INJECTION,
        "critical",
        "SQL boolean-based blind injection",
        r"(?i)\b(?:1\s*=\s*1|1\s*=\s*0|'\s*or\s+'1'\s*=\s*'1|or\s+1\s*=\s*1|and\s+1\s*=\s*1)\b",
    ),
    (
        "SIG-INJ-003",
        ThreatCategory.INJECTION,
        "critical",
        "SQL comment stripping / truncation",
        r"(?:'|--|\*\/|\/\*|#)\s*(?:or|and|union|drop|insert|delete|update|select)\b",
    ),
    (
        "SIG-INJ-004",
        ThreatCategory.INJECTION,
        "critical",
        "SQL stacked queries",
        r";\s*(?:drop|truncate|delete|insert|update|create|alter|exec)\b",
    ),
    (
        "SIG-INJ-005",
        ThreatCategory.INJECTION,
        "high",
        "NoSQL operator injection",
        r"\$(?:where|ne|gt|lt|gte|lte|in|nin|regex|exists|type|mod|all|size|elemMatch|slice)\b",
    ),
    (
        "SIG-INJ-006",
        ThreatCategory.INJECTION,
        "high",
        "LDAP injection",
        r"[)(|&!*\\].*(?:cn|ou|dc|uid|mail|objectclass)\s*=",
    ),
    (
        "SIG-INJ-007",
        ThreatCategory.INJECTION,
        "high",
        "OS command injection via shell metacharacters",
        r"[`$]?\(\s*(?:cat|ls|id|whoami|uname|curl|wget|bash|sh|python|perl|ruby|nc|ncat)\b",
    ),
    (
        "SIG-INJ-008",
        ThreatCategory.INJECTION,
        "high",
        "Server-side template injection",
        r"(?:\{\{.+\}\}|\$\{.+\}|<%.+%>|#\{.+\}|\[\[.+\]\])",
    ),
    (
        "SIG-INJ-009",
        ThreatCategory.INJECTION,
        "critical",
        "XXE / XML external entity",
        r"<!(?:DOCTYPE|ENTITY)\s+[^\s>]+\s+(?:SYSTEM|PUBLIC)\s+",
    ),
    # ── XSS ────────────────────────────────────────────────────────────────
    ("SIG-XSS-001", ThreatCategory.XSS, "high", "Inline script tag", r"<\s*script\b[^>]*>"),
    (
        "SIG-XSS-002",
        ThreatCategory.XSS,
        "high",
        "Event handler injection (onerror, onload, etc.)",
        r"\bon(?:error|load|click|mouse(?:over|out|move)|focus|blur|input|change|submit|keydown|keyup)\s*=",
    ),
    ("SIG-XSS-003", ThreatCategory.XSS, "high", "JavaScript URI scheme", r"javascript\s*:"),
    (
        "SIG-XSS-004",
        ThreatCategory.XSS,
        "medium",
        "Data URI with script content",
        r"data\s*:\s*text/html[^,]*,",
    ),
    (
        "SIG-XSS-005",
        ThreatCategory.XSS,
        "medium",
        "DOM-based eval / innerHTML assignment",
        r"(?:document\.write|innerHTML|outerHTML|insertAdjacentHTML)\s*(?:\(|=)",
    ),
    (
        "SIG-XSS-006",
        ThreatCategory.XSS,
        "high",
        "SVG-based XSS vector",
        r"<\s*svg\b[^>]*>.*?<\s*script\b",
    ),
    # ── PATH TRAVERSAL ──────────────────────────────────────────────────────
    (
        "SIG-PT-001",
        ThreatCategory.PATH_TRAVERSAL,
        "high",
        "Directory traversal: dot-dot-slash",
        r"(?:\.\.[\\/]){2,}",
    ),
    (
        "SIG-PT-002",
        ThreatCategory.PATH_TRAVERSAL,
        "high",
        "URL-encoded directory traversal",
        r"%2e%2e(?:%2f|%5c)",
    ),
    (
        "SIG-PT-003",
        ThreatCategory.PATH_TRAVERSAL,
        "high",
        "Null-byte path injection",
        r"(?:%00|\\x00|\\0)",
    ),
    (
        "SIG-PT-004",
        ThreatCategory.PATH_TRAVERSAL,
        "high",
        "Absolute path to sensitive file",
        r"(?:/etc/(?:passwd|shadow|hosts|sudoers)|/proc/self/|C:\\Windows\\System32\\)",
    ),
    # ── MALWARE / SHELLCODE ─────────────────────────────────────────────────
    (
        "SIG-MAL-001",
        ThreatCategory.MALWARE,
        "critical",
        "EICAR test signature",
        r"X5O!P%@AP\[4\\PZX54\(P\^\)7CC\)7\}\$EICAR-STANDARD-ANTIVIRUS-TEST-FILE",
    ),
    (
        "SIG-MAL-002",
        ThreatCategory.MALWARE,
        "critical",
        "Base64-encoded /bin/sh or /bin/bash shellcode marker",
        r"(?:L2Jpbi9iYXNo|L2Jpbi9zaA==|Y21k)",
    ),
    (
        "SIG-MAL-003",
        ThreatCategory.MALWARE,
        "critical",
        "Reverse shell one-liner (bash, python, ruby, perl)",
        r"bash\s+-[il]\s+>&?\s*/dev/tcp/|python\s+-c\s+['\"]import\s+socket",
    ),
    (
        "SIG-MAL-004",
        ThreatCategory.MALWARE,
        "high",
        "Crypto-miner pool connection string",
        r"(?:stratum\+tcp|xmrig|minerd|cryptonight|monero\.pool)",
    ),
    (
        "SIG-MAL-005",
        ThreatCategory.MALWARE,
        "high",
        "Webshell eval pattern (PHP/ASP)",
        r"(?:eval\s*\(\s*(?:base64_decode|gzinflate|str_rot13|gzuncompress|rawurldecode)|@?eval\s*\(\s*\$_(?:POST|GET|REQUEST|COOKIE))",
    ),
    (
        "SIG-MAL-006",
        ThreatCategory.MALWARE,
        "critical",
        "Windows MZ/PE header (binary executable in text context)",
        r"^MZ",
    ),
    # ── CREDENTIAL LEAK ─────────────────────────────────────────────────────
    (
        "SIG-CRED-001",
        ThreatCategory.CREDENTIAL_LEAK,
        "critical",
        "OpenAI / Anthropic API key pattern",
        r"(?:sk-(?:proj-|ant-|live-|test-)[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{48})",
    ),
    (
        "SIG-CRED-002",
        ThreatCategory.CREDENTIAL_LEAK,
        "critical",
        "AWS access key",
        r"(?:AKIA|AIPA|ASIA|AROA|ANPA|ANVA|AIDA)[A-Z0-9]{16}",
    ),
    (
        "SIG-CRED-003",
        ThreatCategory.CREDENTIAL_LEAK,
        "critical",
        "PEM private key block",
        r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----",
    ),
    (
        "SIG-CRED-004",
        ThreatCategory.CREDENTIAL_LEAK,
        "high",
        "Generic bearer token header",
        r"Authorization:\s*Bearer\s+[A-Za-z0-9_.-]{40,}",
    ),
    (
        "SIG-CRED-005",
        ThreatCategory.CREDENTIAL_LEAK,
        "high",
        "Database connection string with password",
        r"(?:mysql|postgresql|mongodb|redis|amqp)://[^:@\s]+:[^@\s]+@",
    ),
    # ── EXFILTRATION ────────────────────────────────────────────────────────
    (
        "SIG-EXFIL-001",
        ThreatCategory.EXFILTRATION,
        "high",
        "DNS tunnelling pattern (long base32/base64 subdomain)",
        r"[A-Za-z0-9+/]{30,}\.[a-z]{2,6}",
    ),
    (
        "SIG-EXFIL-002",
        ThreatCategory.EXFILTRATION,
        "high",
        "Internal IP range in outbound request",
        r"(?:10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+)",
    ),
    # ── SUSPICIOUS EXEC ─────────────────────────────────────────────────────
    (
        "SIG-EXEC-001",
        ThreatCategory.SUSPICIOUS_EXEC,
        "critical",
        "Python exec() with dynamic argument",
        r"\bexec\s*\(\s*(?:compile|base64|decode|__import__)",
    ),
    (
        "SIG-EXEC-002",
        ThreatCategory.SUSPICIOUS_EXEC,
        "high",
        "subprocess/os.system with shell=True and variable argument",
        r"(?:subprocess\.(?:call|run|Popen)|os\.system)\s*\([^)]*shell\s*=\s*True",
    ),
    (
        "SIG-EXEC-003",
        ThreatCategory.SUSPICIOUS_EXEC,
        "high",
        "Python __import__ abuse",
        r"__import__\s*\(\s*['\"](?:os|subprocess|socket|pty|ctypes)",
    ),
    (
        "SIG-EXEC-004",
        ThreatCategory.SUSPICIOUS_EXEC,
        "high",
        "pickle deserialization of untrusted data",
        r"pickle\.loads?\s*\(",
    ),
    # ── BINARY EXPLOIT ──────────────────────────────────────────────────────
    (
        "SIG-BIN-001",
        ThreatCategory.BINARY_EXPLOIT,
        "critical",
        "NOP sled (x86 shellcode preamble)",
        r"(?:\\x90){10,}",
    ),
    (
        "SIG-BIN-002",
        ThreatCategory.BINARY_EXPLOIT,
        "critical",
        "Format string exploit pattern",
        r"(?:%n|%x|%s){3,}",
    ),
]


class SignatureLibrary:
    """Compiled signature set with fast multi-pattern scan."""

    def __init__(self) -> None:
        self.signatures: List[Signature] = []
        for sid, cat, sev, desc, raw_pattern in _RAW:
            try:
                self.signatures.append(
                    Signature(
                        id=sid,
                        category=cat,
                        severity=sev,
                        description=desc,
                        pattern=_c(raw_pattern),
                    )
                )
            except re.error as e:
                import logging

                logging.getLogger("tranc3.ice_box").warning("Bad signature %s: %s", sid, e)

    def scan(self, content: str) -> list[Signature]:
        """Return all signatures that match *content*."""
        return [sig for sig in self.signatures if sig.pattern.search(content)]

    def __len__(self) -> int:
        return len(self.signatures)


# Module-level singleton — compiled once
_library: SignatureLibrary | None = None


def get_library() -> SignatureLibrary:
    global _library
    if _library is None:
        _library = SignatureLibrary()
    return _library
