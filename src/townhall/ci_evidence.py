"""Read-only independent status verification for one pinned GitHub Actions run.

Checks exact run identity, repository, commit SHA, trusted workflow allowlist,
and successful completion. It does NOT verify build artifacts, security findings,
release approval or provenance and can NEVER authorise PLM advancement.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

_REFERENCE = re.compile(r"gha:([1-9][0-9]{0,17}):([0-9a-fA-F]{40})\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*/[A-Za-z0-9_-][A-Za-z0-9_.-]*\Z")


def verify_run_reference(
    reference: str,
    *,
    trusted_repository: str,
    permitted_workflow_ids: frozenset[int],
    fetch: Callable[[str, int], Mapping[str, Any]],
) -> dict[str, Any]:
    """Inspect externally fetched run data without trusting a submitted PASS."""
    result: dict[str, Any] = {
        "status": "unavailable",
        "reason": "unconfigured",
        "authorization_granted": False,
    }
    if not isinstance(reference, str):
        return dict(result, status="unsupported", reason="invalid_reference")
    matched = _REFERENCE.fullmatch(reference)
    if matched is None:
        return dict(result, status="unsupported", reason="invalid_reference")
    if (
        not isinstance(trusted_repository, str)
        or _REPOSITORY.fullmatch(trusted_repository) is None
        or "/../" in trusted_repository
        or not permitted_workflow_ids
    ):
        return result
    run_id = int(matched.group(1))
    head_sha = matched.group(2).lower()
    # Only the allowlisted fixed repository is sent to fetch; arbitrary
    # URLs, hostnames, and repository names from evidence are never accepted.
    try:
        run = fetch(trusted_repository, run_id)
    except Exception:
        return dict(result, reason="provider_unavailable")
    if not isinstance(run, Mapping):
        return dict(result, status="rejected", reason="malformed_provider_result")

    expected = {
        "id": (run.get("id"), run_id, "run_mismatch"),
        "repository": (
            run.get("repository", {}).get("full_name")
            if isinstance(run.get("repository"), Mapping) else None,
            trusted_repository,
            "repository_mismatch",
        ),
        "head_sha": (run.get("head_sha"), head_sha, "commit_mismatch"),
    }
    for field, (actual, wanted, reason) in expected.items():
        if field in ("repository", "head_sha") and isinstance(actual, str):
            actual = actual.lower()
            wanted = wanted.lower()
        if actual != wanted:
            return dict(result, status="rejected", reason=reason)

    workflow_id = run.get("workflow_id")
    if (
        isinstance(workflow_id, bool)
        or not isinstance(workflow_id, int)
        or workflow_id not in permitted_workflow_ids
    ):
        return dict(result, status="rejected", reason="workflow_not_allowed")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        return dict(result, status="rejected", reason="not_successful")

    return {
        "status": "verified",
        "reason": "matching_successful_workflow_run",
        "run_id": run_id,
        "repository": trusted_repository,
        "head_sha": head_sha,
        "workflow_id": workflow_id,
        "scope": "github_actions_run_status_only",
        "authorization_granted": False,
    }


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            request.full_url, code, "GitHub API redirect refused", headers, fp
        )


def fetch_github_actions_run(repository: str, run_id: int) -> Mapping[str, Any]:
    """Retrieve provider-owned metadata, never accepting a caller URL."""
    token = os.environ.get("TOWNHALL_GITHUB_EVIDENCE_TOKEN")
    if not token:
        raise RuntimeError("GitHub evidence credential unavailable")
    if _REPOSITORY.fullmatch(repository) is None or run_id <= 0:
        raise ValueError("invalid trusted repository or run")
    owner, project = repository.split("/")
    url = f"https://api.github.com/repos/{owner}/{project}/actions/runs/{run_id}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "townhall-evidence-readonly",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    with urllib.request.build_opener(_RejectRedirects()).open(request, timeout=5) as response:
        data = response.read(131073)
    if len(data) > 131072:
        raise ValueError("GitHub evidence payload exceeded maximum size")
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError("unexpected provider response")
    return payload


def configured_run_verification(reference: str) -> dict[str, Any]:
    """Server-owned configuration only. No credential -> no verification."""
    repository = os.environ.get("TOWNHALL_GITHUB_EVIDENCE_REPO", "")
    raw_ids = os.environ.get("TOWNHALL_GITHUB_EVIDENCE_WORKFLOW_IDS", "")
    try:
        ids = frozenset(
            int(segment.strip()) for segment in raw_ids.split(",")
            if segment.strip().isdigit() and int(segment.strip()) > 0
        )
    except (TypeError, ValueError):
        ids = frozenset()
    if not os.environ.get("TOWNHALL_GITHUB_EVIDENCE_TOKEN"):
        ids = frozenset()
    return verify_run_reference(
        reference,
        trusted_repository=repository,
        permitted_workflow_ids=ids,
        fetch=fetch_github_actions_run,
    )
