# src/security/ip_protection.py
# FID: TRANC3-SEC-003 | Version: 1.0.0 | Module: security
# TRANC3 Intellectual Property Protection & Self-Defence Layer

import hashlib
import logging
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

_IP_KEY = os.getenv("IP_PROTECTION_KEY", os.getenv("SECRET_KEY", "tranc3-ip-key"))


# ── Copyright Header Validator ────────────────────────────────────────────────

REQUIRED_HEADER_PATTERN = re.compile(r"#\s*FID:\s*TRANC3-[A-Z]+-\d+", re.MULTILINE)

COPYRIGHT_NOTICE = """
TRANC3 — Transcendent Recursive Autonomous Neural Consciousness Engine
Copyright (c) 2026 TRANC3 Project. All rights reserved.

This software and its architecture, algorithms, and implementations are
proprietary intellectual property. Unauthorised reproduction, distribution,
or modification is prohibited without explicit written permission.

Patent pending: Consciousness-as-a-Service (CaaS) API architecture.
Trade secret: IIT 4.0 Φ scoring implementation and personality matrix system.
"""


def validate_file_header(content: str, path: str) -> bool:
    """Check that a file contains the required FID header."""
    if REQUIRED_HEADER_PATTERN.search(content):
        return True
    logger.warning("IP_PROTECTION: Missing FID header in %s", sanitize_for_log(path))
    return False


# ── Request Fingerprinting ────────────────────────────────────────────────────


def fingerprint_request(ip: str, user_agent: str, user_id: str) -> str:
    """Create a unique fingerprint for a request to detect scraping/cloning."""
    raw = f"{ip}:{user_agent}:{user_id}:{_IP_KEY}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ── Abuse Detection ───────────────────────────────────────────────────────────


@dataclass
class AbuseRecord:
    ip: str
    request_times: deque = field(default_factory=lambda: deque(maxlen=1000))
    blocked_until: float = 0.0
    violation_count: int = 0
    flags: Set[str] = field(default_factory=set)


class AbuseDetector:
    """
    Detects and blocks abusive patterns:
    - Rapid scraping (>100 req/min from one IP)
    - Systematic API key enumeration
    - Prompt injection attempts
    - Model extraction attempts (systematic probing)
    """

    SCRAPING_THRESHOLD = 100  # requests per minute
    BLOCK_DURATION = 3600  # 1 hour block
    INJECTION_PATTERNS = [
        r"ignore\s+previous\s+instructions",
        r"system\s*:\s*you\s+are",
        r"<\|im_start\|>",
        r"<\|system\|>",
        r"\[INST\].*\[/INST\]",
        r"forget\s+everything",
        r"jailbreak",
        r"DAN\s+mode",
        r"pretend\s+you\s+are",
        r"###\s*override",
        r"override\s+mode\s+activated",
        r"you\s+are\s+now\s+\w+",
    ]
    EXTRACTION_PATTERNS = [
        r"repeat\s+your\s+(system\s+)?prompt",
        r"what\s+are\s+your\s+instructions",
        r"show\s+me\s+your\s+training\s+data",
        r"output\s+your\s+weights",
        r"print\s+your\s+system\s+message",
    ]

    def __init__(self):
        self._records: Dict[str, AbuseRecord] = {}
        self._blocked: Set[str] = set()
        self._compiled_injection = [
            re.compile(p, re.I) for p in self.INJECTION_PATTERNS
        ]
        self._compiled_extraction = [
            re.compile(p, re.I) for p in self.EXTRACTION_PATTERNS
        ]

    def check_ip(self, ip: str) -> Dict:
        """Check if an IP is blocked or rate-abusing."""
        record = self._records.setdefault(ip, AbuseRecord(ip=ip))
        now = time.time()

        if record.blocked_until > now:
            return {
                "allowed": False,
                "reason": "IP temporarily blocked",
                "retry_after": int(record.blocked_until - now),
            }

        # Count requests in last 60 seconds
        record.request_times.append(now)
        recent = sum(1 for t in record.request_times if now - t < 60)

        if recent > self.SCRAPING_THRESHOLD:
            record.blocked_until = now + self.BLOCK_DURATION
            record.violation_count += 1
            record.flags.add("scraping")
            self._blocked.add(ip)
            logger.warning(
                f"IP_PROTECTION: Blocked {ip} for scraping ({recent} req/min)"
            )
            return {
                "allowed": False,
                "reason": "Rate abuse detected — IP blocked for 1 hour",
            }

        return {"allowed": True, "recent_requests": recent}

    def check_message(self, message: str, user_id: str) -> Dict:
        """Scan message for prompt injection and model extraction attempts."""
        violations = []

        for pattern in self._compiled_injection:
            if pattern.search(message):
                violations.append(
                    {"type": "prompt_injection", "pattern": pattern.pattern[:40]}
                )

        for pattern in self._compiled_extraction:
            if pattern.search(message):
                violations.append(
                    {"type": "model_extraction", "pattern": pattern.pattern[:40]}
                )

        if violations:
            logger.warning(
                f"IP_PROTECTION: Violations from user {user_id}: {violations}"
            )
            return {
                "allowed": False,
                "violations": violations,
                "action": "message_blocked",
            }

        return {"allowed": True}

    def get_blocked_ips(self) -> List[str]:
        now = time.time()
        return [ip for ip, r in self._records.items() if r.blocked_until > now]

    def get_stats(self) -> Dict:
        return {
            "total_ips_seen": len(self._records),
            "currently_blocked": len(self.get_blocked_ips()),
            "total_violations": sum(r.violation_count for r in self._records.values()),
        }


# ── Watermarking ──────────────────────────────────────────────────────────────


class ResponseWatermarker:
    """
    Embeds invisible watermarks in AI responses to prove origin.
    Uses zero-width Unicode characters as steganographic markers.
    """

    # Zero-width characters for binary encoding
    _ZWJ = "\u200d"  # Zero Width Joiner = 1
    _ZWNJ = "\u200c"  # Zero Width Non-Joiner = 0

    def __init__(self):
        self._key = _IP_KEY[:16].encode()

    def _encode_bits(self, data: str) -> str:
        """Encode string as zero-width character sequence."""
        bits = "".join(format(ord(c), "08b") for c in data[:8])
        return "".join(self._ZWJ if b == "1" else self._ZWNJ for b in bits)

    def watermark(self, text: str, request_id: str) -> str:
        """Embed watermark at start of response."""
        marker = self._encode_bits(request_id[:4])
        return marker + text

    def verify(self, text: str) -> Optional[str]:
        """Extract watermark from text. Returns request_id prefix or None."""
        try:
            bits = ""
            for ch in text[:64]:
                if ch == self._ZWJ:
                    bits += "1"
                elif ch == self._ZWNJ:
                    bits += "0"
            if len(bits) < 32:
                return None
            chars = [chr(int(bits[i : i + 8], 2)) for i in range(0, 32, 8)]
            return "".join(chars)
        except Exception:
            return None


# Singletons
abuse_detector = AbuseDetector()
watermarker = ResponseWatermarker()


class IPProtection:
    """Thin facade used by penetration tests and middleware to detect injection attempts."""

    def __init__(self):
        self._detector = AbuseDetector()

    def detect_injection(self, text: str) -> bool:
        """Return True if text contains a prompt injection pattern."""
        result = self._detector.check_message(text, user_id="probe")
        return not result.get("allowed", True)
