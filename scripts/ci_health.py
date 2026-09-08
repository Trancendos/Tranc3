"""Check canonical workflow health and safely rerun eligible bootstrap failures."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request

CANONICAL_WORKFLOWS = {
    "CI",
    "CodeQL Advanced",
    "Trivy Security Scan",
    "Supply Chain Watch",
    "Frontend Build & Deploy",
}
SAFE_RETRY_STEPS = (
    "install dependencies",
    "install ruff",
    "install pyyaml",
    "restore cache",
    "setup python",
)


def request(path: str, method: str = "GET", body: bytes | None = None) -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    request_obj = urllib.request.Request(
        f"https://api.github.com{path}",
        data=body,
        method=method,
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request_obj, timeout=20) as response:
        payload = response.read()
    return json.loads(payload) if payload else {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--remediate-run-id", type=int)
    args = parser.parse_args()
    repository = os.environ["GITHUB_REPOSITORY"]
    runs = request(f"/repos/{repository}/actions/runs?per_page=50").get("workflow_runs", [])
    canonical = [run for run in runs if run.get("name") in CANONICAL_WORKFLOWS]
    failures = [run for run in canonical if run.get("conclusion") == "failure"]
    print("## CI health")
    print(f"- Canonical runs inspected: {len(canonical)}")
    print(f"- Failed canonical runs: {len(failures)}")
    for run in canonical[:10]:
        print(f"- {run['name']}: {run.get('conclusion') or run.get('status')} ({run['html_url']})")

    if args.remediate_run_id:
        run = next((item for item in canonical if item.get("id") == args.remediate_run_id), None)
        if not run or run.get("conclusion") != "failure" or run.get("run_attempt", 1) != 1:
            raise SystemExit("Refusing remediation: run is not a first-attempt canonical failure")
        jobs = request(f"/repos/{repository}/actions/runs/{args.remediate_run_id}/jobs").get(
            "jobs", []
        )
        failed_steps = [
            step.get("name", "").lower()
            for job in jobs
            if job.get("conclusion") == "failure"
            for step in job.get("steps", [])
            if step.get("conclusion") == "failure"
        ]
        if not failed_steps or not all(
            any(marker in step for marker in SAFE_RETRY_STEPS) for step in failed_steps
        ):
            raise SystemExit(
                "Refusing remediation: failed step is not a dependency/bootstrap failure"
            )
        request(
            f"/repos/{repository}/actions/runs/{args.remediate_run_id}/rerun-failed-jobs",
            method="POST",
        )
        print(f"- Remediation dispatched for run {args.remediate_run_id}")
        return 0

    return 1 if len(failures) >= 3 else 0


if __name__ == "__main__":
    raise SystemExit(main())
