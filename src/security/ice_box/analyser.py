"""
Ice Box — Threat Analyser
==========================
Orchestrates signature scanning, entropy analysis, and file-type heuristics
to produce a ThreatVerdict for arbitrary content.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from src.security.ice_box.signatures import Signature, ThreatCategory, get_library


class ThreatVerdict(Enum):
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    MALICIOUS = "malicious"
    QUARANTINED = "quarantined"


@dataclass
class ThreatFinding:
    signature_id: str
    category: ThreatCategory
    severity: str
    description: str
    matched_text: str = ""

    @property
    def is_critical(self) -> bool:
        return self.severity == "critical"


@dataclass
class AnalysisReport:
    content_hash: str
    verdict: ThreatVerdict
    findings: List[ThreatFinding]
    entropy: float
    content_length: int
    analysis_ms: float
    high_entropy: bool = False
    suspicious_binary: bool = False
    error: Optional[str] = None

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "high")


def _shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts: dict[int, int] = {}
    for b in data:
        counts[b] = counts.get(b, 0) + 1
    length = len(data)
    entropy = 0.0
    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


# Known binary file magic bytes that are suspicious in text contexts
_BINARY_MAGIC: list[bytes] = [
    b"MZ",           # Windows PE
    b"\x7fELF",      # Linux ELF
    b"\xca\xfe\xba\xbe",  # Mach-O
    b"PK\x03\x04",   # ZIP (potential zip-slip vector)
    b"%PDF",         # PDF (potential embedded script)
    b"\xff\xd8\xff", # JPEG
    b"\x89PNG",      # PNG
]

_NULL_BYTE_RE = re.compile(rb"\x00{4,}")


class ThreatAnalyser:
    """
    Static content analyser. Thread-safe; holds no mutable state between calls.
    """

    # Entropy thresholds
    HIGH_ENTROPY_THRESHOLD = 5.5   # packed/encrypted/b64 shellcode indicator
    BINARY_ENTROPY_THRESHOLD = 7.0  # near-random binary content

    def analyse(self, content: str | bytes, *, source: str = "") -> AnalysisReport:
        t0 = time.monotonic()

        raw: bytes = content.encode("utf-8", errors="replace") if isinstance(content, str) else content
        text: str = raw.decode("utf-8", errors="replace")

        content_hash = hashlib.sha256(raw).hexdigest()
        entropy = _shannon_entropy(raw)
        high_entropy = entropy >= self.HIGH_ENTROPY_THRESHOLD
        suspicious_binary = self._is_suspicious_binary(raw)

        findings: list[ThreatFinding] = []

        # Signature scan
        library = get_library()
        for sig in library.scan(text):
            match = sig.pattern.search(text)
            matched = match.group(0)[:120] if match else ""
            findings.append(ThreatFinding(
                signature_id=sig.id,
                category=sig.category,
                severity=sig.severity,
                description=sig.description,
                matched_text=matched,
            ))

        # Entropy-based synthetic finding
        if entropy >= self.BINARY_ENTROPY_THRESHOLD and len(raw) > 64:
            findings.append(ThreatFinding(
                signature_id="SIG-ENT-001",
                category=ThreatCategory.MALWARE,
                severity="high",
                description=f"Near-random entropy ({entropy:.2f} bits/byte) — possible encrypted/packed payload",
            ))

        # Binary magic in non-binary context
        if suspicious_binary:
            findings.append(ThreatFinding(
                signature_id="SIG-BIN-003",
                category=ThreatCategory.BINARY_EXPLOIT,
                severity="high",
                description="Binary file magic bytes detected in text context",
            ))

        verdict = self._verdict(findings)
        duration_ms = (time.monotonic() - t0) * 1000

        return AnalysisReport(
            content_hash=content_hash,
            verdict=verdict,
            findings=findings,
            entropy=entropy,
            content_length=len(raw),
            analysis_ms=duration_ms,
            high_entropy=high_entropy,
            suspicious_binary=suspicious_binary,
        )

    def _is_suspicious_binary(self, data: bytes) -> bool:
        for magic in _BINARY_MAGIC:
            if data.startswith(magic):
                return True
        # Excessive null bytes = likely binary
        if _NULL_BYTE_RE.search(data):
            return True
        return False

    def _verdict(self, findings: list[ThreatFinding]) -> ThreatVerdict:
        if not findings:
            return ThreatVerdict.CLEAN
        severities = {f.severity for f in findings}
        if "critical" in severities:
            return ThreatVerdict.MALICIOUS
        if "high" in severities:
            return ThreatVerdict.MALICIOUS
        if "medium" in severities:
            return ThreatVerdict.SUSPICIOUS
        return ThreatVerdict.SUSPICIOUS
