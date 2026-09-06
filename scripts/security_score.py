#!/usr/bin/env python3
"""
Compute Security dimension score for production_readiness_score.py.

Inputs (best-effort, no network required):
  - SECURITY_ALERT_REGISTER.md completeness
  - tests/test_url_validation.py presence + pytest result
  - pre_deploy gate bandit/pip-audit signals from logs if present
  - Dockerfile non-root checks for ffmpeg-worker
  - K8s securityContext coverage in key manifests
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
REGISTER = ROOT / "SECURITY_ALERT_REGISTER.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _pytest_url_validation() -> tuple[bool, str]:
    test_file = ROOT / "tests" / "test_url_validation.py"
    if not test_file.is_file():
        return False, "missing test_url_validation.py"
    try:
        proc = subprocess.run(  # nosec B603 — list args, no shell=True
            [sys.executable, "-m", "pytest", str(test_file), "-q", "--tb=no"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        ok = proc.returncode == 0
        return ok, "pass" if ok else (proc.stdout + proc.stderr)[-400:]
    except Exception as exc:
        return False, str(exc)


def _ffmpeg_non_root() -> bool:
    text = _read(ROOT / "workers" / "ffmpeg-worker" / "Dockerfile")
    return "USER" in text and "tranc3" in text.lower()


def _k8s_manifest_hardened(rel_path: str) -> bool:
    text = _read(ROOT / rel_path)
    if not text:
        return False
    return (
        "runAsNonRoot: true" in text
        and "readOnlyRootFilesystem: true" in text
        and "seccompProfile:" in text
        and "RuntimeDefault" in text
    )


def _igi_gitops_hardened() -> bool:
    return _k8s_manifest_hardened("src/nanoservices/igi_gitops/flux/base/deployments.yaml")


def _flux_base_hardened() -> bool:
    return _k8s_manifest_hardened("flux/base/deployments.yaml")


def _zero_cost_chains_valid() -> bool:
    try:
        sys.path.insert(0, str(ROOT))
        from src.zero_cost.registry import validate_all_chains

        return len(validate_all_chains()) == 0
    except Exception:
        return False


def _register_complete() -> bool:
    text = _read(REGISTER)
    required = ("FIX", "FP", "ACCEPT", "SUPPRESS")
    return all(s in text for s in required) and "hostIPC" in text


def _bandit_clean_signal() -> bool:
    """True if last gate run reported no HIGH bandit issues."""
    gate_log = LOGS / "pre_deploy_gate.json"
    if gate_log.is_file():
        try:
            data = json.loads(gate_log.read_text())
            return data.get("bandit_high", 1) == 0
        except json.JSONDecodeError:
            pass
    return True  # unknown — neutral


def _bandit_baseline_drift() -> tuple[bool | None, str]:
    """Compare measured bandit findings with the stored `.security-baseline`.

    Returns ``(within_tolerance, detail)``. A ``None`` first element means
    "unknown" (no measured data available) and is treated as neutral — it never
    fails the score. This mirrors the drift check in
    ``.forgejo/workflows/security-baseline.yml`` so the production-readiness
    score and the CI ratchet agree on whether the baseline is still meaningful.

    A stale baseline that over-counts findings is silent in the ratchet: the
    gate keeps passing while providing no real protection. Surfacing the drift
    here makes that blind spot visible in the Security dimension.
    """
    baseline_path = ROOT / ".security-baseline"
    if not baseline_path.is_file():
        return None, "no .security-baseline"
    try:
        # Read EVERY assignment, not just the first. A file with two of them is
        # rejected by .forgejo/workflows/security-baseline.yml, and a parser
        # here that silently took the first would let the two controls disagree
        # about the same file. `int()` also accepts "-1", which would then be
        # treated as a zero baseline, so require digits only.
        values = [
            line.split("=", 1)[1].strip()
            for line in baseline_path.read_text().splitlines()
            if line.startswith("bandit_findings=")
        ]
    except (OSError, UnicodeDecodeError):
        return None, "unreadable .security-baseline"
    if not values:
        return None, ".security-baseline missing bandit_findings="
    if len(values) > 1:
        return None, f".security-baseline has {len(values)} bandit_findings= lines (need exactly 1)"
    # `str.isdigit()` is TRUE for characters `int()` refuses: "\u00b2".isdigit()
    # is True but int("\u00b2") raises ValueError. Requiring ASCII first keeps the
    # rejection of "-1" that isdigit() was chosen for, without the crash.
    if not (values[0].isascii() and values[0].isdigit()):
        return (
            None,
            f".security-baseline bandit_findings={values[0]!r} is not a non-negative integer",
        )
    baseline = int(values[0])

    # Two workflows produce this report under different names:
    # security-baseline.yml writes bandit-full.json, security-scan.yml writes
    # bandit-results.json -- and security-scan.yml also runs this script.
    # Reading only one name made the drift check silently neutral in the other
    # workflow: a control that runs, reports, and measures nothing.
    bandit_log = next(
        (p for p in (LOGS / "bandit-full.json", LOGS / "bandit-results.json") if p.is_file()),
        None,
    )
    if bandit_log is None:
        return None, "no bandit report in logs/ (run bandit to compare)"
    try:
        payload = json.loads(bandit_log.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None, f"unreadable {bandit_log.name}"
    # A JSON list or scalar would raise AttributeError on .get, and
    # `"results": null` would raise TypeError in len(). Neither should crash a
    # scorecard; both mean "cannot measure", which is already a neutral answer.
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return None, f"{bandit_log.name} is not a bandit report (no results list)"
    measured = len(payload["results"])

    if baseline <= 0:
        return True, f"baseline zero (measured {measured})"
    delta = baseline - measured
    # Whole-percent, half-up -- byte-for-byte the arithmetic in
    # .forgejo/workflows/security-baseline.yml:
    #   DRIFT=$(( (DELTA_ABS * 100 + BASELINE / 2) / BASELINE ))
    # Rounding to one decimal here made the two controls disagree on the same
    # scan: baseline 201 / measured 180 is 10% to the workflow (pass) and 10.4%
    # to this script (stale). Two security controls reporting different verdicts
    # from identical input is worse than either verdict being slightly coarse.
    drift = (abs(delta) * 100 + baseline // 2) // baseline
    within = drift <= 10
    return within, f"baseline {baseline}, measured {measured}, drift {drift}%"


CENSUS_PATH = ROOT / "logs" / "vulnerability_census.json"


def _dependency_vulnerabilities() -> tuple[bool, str, int]:
    """(ok, detail, fixable_count) from the vulnerability census.

    Reads scripts/vulnerability_census.py's output rather than scanning here:
    the scan takes minutes across six manifests and needs the network, and this
    function is called every time anyone asks for a score.

    A MISSING census is not a pass. Before this existed, every check in this file
    was a presence check -- register exists, SSRF module exists, bandit signals --
    so the dimension reported 100% while thirty-one vulnerabilities were open on
    the default branch. Treating an absent census as "fine" would rebuild exactly
    that blind spot one level up.
    """
    if not CENSUS_PATH.is_file():
        return False, "no census — run scripts/vulnerability_census.py", -1
    try:
        data = json.loads(CENSUS_PATH.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"census unreadable: {exc}", -1
    # Every field is required and type-checked. `data.get("fixable_count", 0)`
    # would read a truncated census -- or `{"scanned_ok": true}` -- as zero open
    # vulnerabilities, passing the check and skipping the cap. That is a fail-open
    # in the one control whose entire purpose is to fail closed.
    if not isinstance(data, dict) or not isinstance(data.get("scanned_ok"), bool):
        return False, "census invalid: scanned_ok missing or not a boolean", -1
    for field in ("fixable_count", "accepted_count"):
        value = data.get(field)
        # bool is a subclass of int, and `True` must not read as a count of 1.
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False, f"census invalid: {field} is not a non-negative integer", -1
    if not data["scanned_ok"]:
        errored = ", ".join(data.get("errored_surfaces", [])) or "unknown"
        return False, f"census incomplete (errored: {errored})", -1
    fixable = data["fixable_count"]
    accepted = data["accepted_count"]
    # Read with .get, and deliberately NOT added to the required-field check above:
    # a census written before the blocked classification existed is still a valid
    # census, and demanding the field would turn an older artefact into an error.
    blocked = data.get("blocked_count", 0)
    blocked_note = f", {blocked} blocked upstream" if blocked else ""
    # Name the scope. The production gate runs the census with --scope core (root
    # manifests only); without this the Security dimension reads as a whole-estate
    # result while measuring a subset. Absent on a census written before scopes
    # existed, hence the default rather than a required field.
    scope = data.get("scope", "unknown")
    detail = (
        f"{fixable} fixable, {accepted} accepted{blocked_note} "
        f"(scope {scope}, {data.get('generated_at', '?')})"
    )
    return fixable == 0, detail, fixable


def compute_security_dimension() -> dict:
    # Computed once: this reads and parses a JSON file, and calling it twice
    # also risks the check and the reported detail disagreeing if the census is
    # rewritten between the two reads.
    vulns_ok, vuln_detail, fixable = _dependency_vulnerabilities()

    checks: list[tuple[str, float, bool]] = [
        ("security_alert_register", 12.0, _register_complete()),
        ("url_validation_tests", 20.0, _pytest_url_validation()[0]),
        ("ffmpeg_non_root", 12.0, _ffmpeg_non_root()),
        ("igi_gitops_security_context", 12.0, _igi_gitops_hardened()),
        ("flux_base_security_context", 12.0, _flux_base_hardened()),
        ("zero_cost_chains_valid", 12.0, _zero_cost_chains_valid()),
        ("hostipc_documented", 8.0, (ROOT / "docs" / "HOSTIPC_RISK_ACCEPTANCE.md").is_file()),
        ("ssrf_module_present", 7.0, (ROOT / "Dimensional" / "url_validation.py").is_file()),
        ("trivyignore_documented", 5.0, (ROOT / ".trivyignore").is_file()),
        ("bandit_gate_signal", 5.0, _bandit_clean_signal()),
        # Weighted heaviest of any single check: an open, fixable CVE is a
        # worse security state than any missing document on this list.
        ("no_fixable_dependency_vulns", 30.0, vulns_ok),
    ]

    score = sum(w for _, w, ok in checks if ok)
    max_score = sum(w for _, w, _ in checks)
    percent = round(100.0 * score / max_score, 1) if max_score else 0.0

    details = {name: ok for name, _, ok in checks}
    _, pytest_detail = _pytest_url_validation()
    details["url_validation_tests_detail"] = pytest_detail

    details["dependency_vulnerabilities_detail"] = vuln_detail

    drift_ok, drift_detail = _bandit_baseline_drift()
    details["bandit_baseline_drift"] = drift_detail
    # A stale baseline (drift beyond tolerance) means the ratchet gate is not
    # providing meaningful protection; flag it honestly rather than letting the
    # dimension read as healthy by default.
    if drift_ok is False:
        details["bandit_baseline_drift_stale"] = True

    # Hard cap, not just a weight. With weighting alone a repo could still show
    # ~90% -- a green status -- while shipping known-exploitable dependencies,
    # because the other ten checks are easy to satisfy and never regress. The cap
    # makes "green" mean what a reader assumes it means.
    capped = False
    if not vulns_ok:
        percent = min(percent, 89.9)
        capped = True

    return {
        "dimension": "Security",
        "score_percent": percent,
        "weight": 0.10,
        "checks": details,
        "score_capped_by_open_vulnerabilities": capped,
        "fixable_vulnerability_count": fixable,
        "honest_note": (
            "Config checks derive from repo artifacts and local pytest; not a live Forgejo "
            "API sync. The vulnerability figure comes from logs/vulnerability_census.json "
            "and caps this score below green whenever a fixable CVE is open or the census "
            "could not be read. The bandit baseline drift (bandit_baseline_drift) is "
            "comparative only: it warns when .security-baseline diverges from a measured "
            "bandit run, exposing a ratchet that has gone stale."
        ),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Compute repo-weighted Security dimension score")
    parser.add_argument(
        "--min-percent",
        type=float,
        default=0.0,
        help="Exit 1 if score_percent is below this threshold (e.g. 90 for production gate)",
    )
    args = parser.parse_args()

    LOGS.mkdir(parents=True, exist_ok=True)
    result = compute_security_dimension()
    out = LOGS / "security_score.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))

    threshold = args.min_percent
    score = result.get("score_percent", 0.0)
    if threshold > 0 and score < threshold:
        print(
            f"FAIL: Security dimension {score}% < required {threshold}%",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
