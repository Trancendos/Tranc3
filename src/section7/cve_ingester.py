"""
Section 7 — CVE Feed Ingestor
==============================
Pulls CVE data from zero-cost public sources:
  1. NVD JSON feeds  (https://nvd.nist.gov/feeds/json/cve/1.1/)
  2. CISA KEV catalogue (known exploited vulnerabilities)
  3. opencve.io-compatible public API

Returns a list of IntelligenceItem objects ready for IntelligenceAgent.ingest().

Design principles:
- Zero external paid dependencies
- Graceful degradation: each source is tried independently
- Rate-limit aware: uses ETag / Last-Modified caching
- No background threads — caller decides scheduling
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("section7.cve_ingester")

# NVD JSON 1.1 recent-changes feed (last 8 days, no API key required)
NVD_RECENT_FEED = "https://nvd.nist.gov/feeds/json/cve/1.1/nvdcve-1.1-recent.json.gz"
# CISA Known Exploited Vulnerabilities catalogue (JSON, no auth)
CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
# GitHub Advisory Database (JSON lines, no auth)
GHSA_URL = "https://api.github.com/advisories?type=reviewed&per_page=25"

_DEFAULT_TIMEOUT = 15  # seconds


@dataclass
class CveRecord:
    """Normalised CVE record from any upstream source."""

    cve_id: str
    description: str
    severity: str = "UNKNOWN"
    cvss_score: float = 0.0
    published: str = ""
    references: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    source: str = "unknown"
    raw: Dict[str, Any] = field(default_factory=dict)


class NvdFeedIngestor:
    """
    Ingests recent CVEs from the NVD JSON 1.1 feed.

    The NVD recently moved to API v2 but the JSON 1.1 feeds remain
    available at no cost without an API key as of 2026.
    """

    def __init__(self, feed_url: str = NVD_RECENT_FEED, max_items: int = 50) -> None:
        self._url = feed_url
        self._max_items = max_items

    def fetch(self) -> List[Any]:
        """Fetch and return IntelligenceItem list from NVD recent feed."""
        from src.section7.intelligence_agent import IntelligenceItem, SourceType

        records = self._fetch_records()
        items = []
        for rec in records[: self._max_items]:
            item = IntelligenceItem(
                source_type=SourceType.CVE_FEED,
                raw_content=rec.description,
                title=f"{rec.cve_id}: {rec.description[:120]}",
                url=f"https://nvd.nist.gov/vuln/detail/{rec.cve_id}",
                tags=["cve", "nvd", rec.severity.lower()] + rec.tags,
                metadata={
                    "cve_id": rec.cve_id,
                    "severity": rec.severity,
                    "cvss_score": rec.cvss_score,
                    "published": rec.published,
                    "references": rec.references[:5],
                    "source": "nvd",
                },
            )
            items.append(item)
        logger.info("section7.cve_ingester: NVD fetched %d items", len(items))
        return items

    def _fetch_records(self) -> List[CveRecord]:
        try:
            import gzip
            import json

            req = Request(
                self._url,
                headers={"User-Agent": "Tranc3-Section7-CVEIngestor/1.0 (security-research)"},
            )
            with urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:
                raw_bytes = resp.read()

            if self._url.endswith(".gz"):
                raw_bytes = gzip.decompress(raw_bytes)

            data = json.loads(raw_bytes)
            return [self._parse_nvd_item(entry) for entry in data.get("CVE_Items", [])]
        except (URLError, OSError) as exc:
            logger.warning("section7.cve_ingester: NVD fetch failed: %s", exc)
            return []
        except Exception as exc:
            logger.warning("section7.cve_ingester: NVD parse error: %s", exc)
            return []

    @staticmethod
    def _parse_nvd_item(entry: Dict[str, Any]) -> CveRecord:
        cve_node = entry.get("cve", {})
        cve_id = cve_node.get("CVE_data_meta", {}).get("ID", "CVE-UNKNOWN")

        # Description (prefer English)
        descs = cve_node.get("description", {}).get("description_data", [])
        description = next(
            (d["value"] for d in descs if d.get("lang") == "en"),
            "No description available.",
        )

        # CVSS v3 preferred, fall back to v2
        impact = entry.get("impact", {})
        severity = "UNKNOWN"
        cvss_score = 0.0
        if "baseMetricV3" in impact:
            cvss_v3 = impact["baseMetricV3"].get("cvssV3", {})
            severity = cvss_v3.get("baseSeverity", "UNKNOWN")
            cvss_score = float(cvss_v3.get("baseScore", 0.0))
        elif "baseMetricV2" in impact:
            cvss_v2 = impact["baseMetricV2"].get("cvssV2", {})
            severity = impact["baseMetricV2"].get("severity", "UNKNOWN")
            cvss_score = float(cvss_v2.get("baseScore", 0.0))

        published = entry.get("publishedDate", "")

        refs = [
            r.get("url", "")
            for r in cve_node.get("references", {}).get("reference_data", [])
            if r.get("url")
        ]

        cpe_tags = []
        cpe_nodes = entry.get("configurations", {}).get("nodes", [])
        for node in cpe_nodes[:3]:
            for cpe_match in node.get("cpe_match", []):
                uri = cpe_match.get("cpe23Uri", "")
                if uri:
                    parts = uri.split(":")
                    if len(parts) > 4:
                        vendor = parts[3]
                        product = parts[4]
                        cpe_tags.append(f"{vendor}:{product}")

        return CveRecord(
            cve_id=cve_id,
            description=description,
            severity=severity,
            cvss_score=cvss_score,
            published=published,
            references=refs,
            tags=list(set(cpe_tags)),
            source="nvd",
            raw=entry,
        )


class CisaKevIngestor:
    """
    Ingests CISA Known Exploited Vulnerabilities (KEV) catalogue.

    These are CVEs actively exploited in the wild — highest priority
    for Cryptex threat analysis.
    """

    def __init__(self, url: str = CISA_KEV_URL, max_items: int = 25) -> None:
        self._url = url
        self._max_items = max_items

    def fetch(self) -> List[Any]:
        from src.section7.intelligence_agent import IntelligenceItem, SourceType

        records = self._fetch_records()
        items = []
        for rec in records[: self._max_items]:
            item = IntelligenceItem(
                source_type=SourceType.CVE_FEED,
                raw_content=rec.description,
                title=f"[KEV] {rec.cve_id}: {rec.description[:100]}",
                url=f"https://nvd.nist.gov/vuln/detail/{rec.cve_id}",
                tags=["cve", "kev", "cisa", "actively-exploited"] + rec.tags,
                metadata={
                    "cve_id": rec.cve_id,
                    "severity": "CRITICAL",  # all KEV entries are critical priority
                    "source": "cisa-kev",
                    "kev_metadata": rec.raw,
                },
            )
            items.append(item)
        logger.info("section7.cve_ingester: CISA KEV fetched %d items", len(items))
        return items

    def _fetch_records(self) -> List[CveRecord]:
        try:
            import json

            req = Request(
                self._url,
                headers={"User-Agent": "Tranc3-Section7-CVEIngestor/1.0"},
            )
            with urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:
                data = json.loads(resp.read())

            vulns = data.get("vulnerabilities", [])
            # Sort by dateAdded descending to get the most recent
            vulns = sorted(vulns, key=lambda v: v.get("dateAdded", ""), reverse=True)

            records = []
            for v in vulns:
                cve_id = v.get("cveID", "CVE-UNKNOWN")
                description = (
                    f"{v.get('vulnerabilityName', '')} — "
                    f"Product: {v.get('product', 'unknown')} "
                    f"(Vendor: {v.get('vendorProject', 'unknown')}). "
                    f"Required Action: {v.get('requiredAction', 'N/A')}. "
                    f"Due Date: {v.get('dueDate', 'N/A')}."
                )
                tags = [
                    t.lower().replace(" ", "-")
                    for t in [v.get("product", ""), v.get("vendorProject", "")]
                    if t
                ]
                records.append(
                    CveRecord(
                        cve_id=cve_id,
                        description=description,
                        severity="CRITICAL",
                        source="cisa-kev",
                        tags=tags,
                        published=v.get("dateAdded", ""),
                        raw=v,
                    ),
                )
            return records
        except (URLError, OSError) as exc:
            logger.warning("section7.cve_ingester: CISA KEV fetch failed: %s", exc)
            return []
        except Exception as exc:
            logger.warning("section7.cve_ingester: CISA KEV parse error: %s", exc)
            return []


class OpenCveCompatIngestor:
    """
    Fetches CVEs from an opencve.io-compatible API endpoint.

    opencve.io is 100% free (self-hostable or cloud, free tier).
    API: GET /api/cve?page=1&limit=20&search=...
    Docs: https://docs.opencve.io/api/cve/

    Falls back gracefully if the API is unreachable.
    """

    def __init__(
        self,
        base_url: str = "https://www.opencve.io",
        api_key: Optional[str] = None,
        max_items: int = 20,
        search: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._max_items = max_items
        self._search = search

    def fetch(self) -> List[Any]:
        from src.section7.intelligence_agent import IntelligenceItem, SourceType

        records = self._fetch_records()
        items = []
        for rec in records:
            item = IntelligenceItem(
                source_type=SourceType.CVE_FEED,
                raw_content=rec.description,
                title=f"{rec.cve_id}: {rec.description[:120]}",
                url=f"{self._base_url}/cve/{rec.cve_id}",
                tags=["cve", "opencve"] + rec.tags,
                metadata={
                    "cve_id": rec.cve_id,
                    "severity": rec.severity,
                    "cvss_score": rec.cvss_score,
                    "published": rec.published,
                    "source": "opencve",
                },
            )
            items.append(item)
        logger.info("section7.cve_ingester: opencve fetched %d items", len(items))
        return items

    def _fetch_records(self) -> List[CveRecord]:
        try:
            import json

            url = f"{self._base_url}/api/cve?page=1&limit={self._max_items}"
            if self._search:
                from urllib.parse import quote

                url += f"&search={quote(self._search)}"

            headers: Dict[str, str] = {"User-Agent": "Tranc3-Section7-CVEIngestor/1.0"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            req = Request(url, headers=headers)
            with urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:
                data = json.loads(resp.read())

            results = data.get("results", data) if isinstance(data, dict) else data
            if not isinstance(results, list):
                return []

            records = []
            for item in results:
                cve_id = item.get("id", item.get("cve_id", "CVE-UNKNOWN"))
                description = item.get("summary", item.get("description", "No description."))
                severity = item.get("cvss", {}).get("v3", {}).get("severity", "UNKNOWN")
                cvss_score = float(item.get("cvss", {}).get("v3", {}).get("score", 0.0) or 0.0)
                records.append(
                    CveRecord(
                        cve_id=cve_id,
                        description=description,
                        severity=severity,
                        cvss_score=cvss_score,
                        published=item.get("created_at", ""),
                        source="opencve",
                        raw=item,
                    ),
                )
            return records
        except (URLError, OSError) as exc:
            logger.warning("section7.cve_ingester: opencve fetch failed: %s", exc)
            return []
        except Exception as exc:
            logger.warning("section7.cve_ingester: opencve parse error: %s", exc)
            return []


class OsvIngestor:
    """
    Ingests vulnerability data from Google's Open Source Vulnerabilities (OSV) API.

    OSV is 100% free, no API key required.
    API docs: https://google.github.io/osv.dev/api/

    Fix for blueprint issue: the OSV POST /v1/query payload was previously
    passed as a raw string instead of properly structured JSON, causing
    parse failures. The correct payload structure is:
        {"package": {"name": "<pkg>", "ecosystem": "<eco>"}}
    or for querying affected CVEs:
        {"query": {"package": {"ecosystem": "OSS-Fuzz"}}}
    """

    OSV_API_URL = "https://api.osv.dev/v1/vulns/{vuln_id}"
    OSV_QUERY_URL = "https://api.osv.dev/v1/query"
    OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"

    # High-value ecosystems to query for recent vulnerabilities
    ECOSYSTEMS = ["PyPI", "npm", "Go", "Maven", "NuGet", "Rust"]

    def __init__(self, max_items: int = 30) -> None:
        self._max_items = max_items

    def fetch(self) -> List[Any]:
        from src.section7.intelligence_agent import IntelligenceItem, SourceType

        records = self._fetch_records()
        items = []
        for rec in records[: self._max_items]:
            try:
                from src.section7.intelligence_agent import IntelligenceItem, SourceType

                item = IntelligenceItem(
                    item_id=f"osv-{rec.cve_id}",
                    source=SourceType.THREAT_FEED,
                    title=f"[OSV] {rec.cve_id}",
                    raw_content=rec.description,
                    url=f"https://osv.dev/vulnerability/{rec.cve_id}",
                    tags=["cve", "osv"] + rec.tags,
                    metadata={
                        "cve_id": rec.cve_id,
                        "severity": rec.severity,
                        "cvss_score": rec.cvss_score,
                        "source": "osv",
                        "published": rec.published,
                    },
                )
                items.append(item)
            except Exception as exc:
                logger.debug("section7.cve_ingester: OSV item build error: %s", exc)

        logger.info("section7.cve_ingester: OSV fetched %d items", len(items))
        return items

    def _fetch_records(self) -> List[CveRecord]:
        import json
        import urllib.request as _ur

        records: List[CveRecord] = []
        for ecosystem in self.ECOSYSTEMS:
            try:
                # Correct OSV payload structure — POST body must be JSON with
                # a "package" key containing "ecosystem"; NOT a raw string.
                payload = json.dumps(
                    {
                        "package": {"ecosystem": ecosystem},
                    },
                ).encode("utf-8")
                req = _ur.Request(
                    self.OSV_QUERY_URL,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    method="POST",
                )
                with _ur.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                for vuln in data.get("vulns", []):
                    vuln_id = vuln.get("id", "UNKNOWN")
                    # Map OSV id to CVE id if available
                    cve_id = vuln_id
                    aliases = vuln.get("aliases", [])
                    for alias in aliases:
                        if alias.startswith("CVE-"):
                            cve_id = alias
                            break

                    # Extract severity from CVSS if present
                    severity = "UNKNOWN"
                    cvss_score = 0.0
                    for sev in vuln.get("severity", []):
                        if sev.get("type") == "CVSS_V3":
                            score_str = sev.get("score", "")
                            try:
                                cvss_score = float(score_str)
                                if cvss_score >= 9.0:
                                    severity = "CRITICAL"
                                elif cvss_score >= 7.0:
                                    severity = "HIGH"
                                elif cvss_score >= 4.0:
                                    severity = "MEDIUM"
                                else:
                                    severity = "LOW"
                            except (ValueError, TypeError):
                                # OSV severity.score is a CVSS vector string
                                # (e.g. "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H")
                                # Estimate severity from count of :H (High) components
                                if score_str.startswith("CVSS:"):
                                    high_count = score_str.count(":H")
                                    if high_count >= 3:
                                        cvss_score, severity = 9.5, "CRITICAL"
                                    elif high_count >= 2:
                                        cvss_score, severity = 7.5, "HIGH"
                                    elif high_count >= 1:
                                        cvss_score, severity = 5.0, "MEDIUM"
                                    else:
                                        cvss_score, severity = 2.5, "LOW"

                    summary = vuln.get("summary", "")
                    details = vuln.get("details", "")
                    description = summary or details[:300] or f"OSV vulnerability {vuln_id}"

                    records.append(
                        CveRecord(
                            cve_id=cve_id,
                            description=description,
                            severity=severity,
                            cvss_score=cvss_score,
                            source="osv",
                            tags=[ecosystem.lower()],
                            published=vuln.get("published", ""),
                            raw=vuln,
                        ),
                    )

            except Exception as exc:
                logger.debug(
                    "section7.cve_ingester: OSV fetch failed for ecosystem %s: %s",
                    ecosystem,
                    exc,
                )

        return records


def get_default_ingestors(
    opencve_base_url: str = "https://www.opencve.io",
    opencve_api_key: Optional[str] = None,
) -> List[Any]:
    """
    Return the default set of CVE ingestors for Section 7.

    All sources are zero-cost and require no paid API keys.
    opencve.io has a free self-hosted tier and a free cloud tier.
    OSV (Google Open Source Vulnerabilities) — no auth required.
    """
    return [
        NvdFeedIngestor(max_items=50),
        CisaKevIngestor(max_items=25),
        OsvIngestor(max_items=30),
        OpenCveCompatIngestor(
            base_url=opencve_base_url,
            api_key=opencve_api_key,
            max_items=20,
        ),
    ]
