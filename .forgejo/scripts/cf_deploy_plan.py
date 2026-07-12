#!/usr/bin/env python3
"""Compute the Cloudflare deploy matrix for the deploy-cloudflare workflow.

Smart-logic planner: rather than a fixed set of hardcoded jobs, this reads
`cloudflare/deploy-manifest.json` and decides *which* workers actually need
deploying, so a change touching one worker (or a docs-only change under
`cloudflare/`) doesn't blindly redeploy everything.

Selection rules (first match wins):
  * `workflow_dispatch` with input `worker` != "all"  -> just that worker.
  * `workflow_dispatch` with input `worker` == "all"   -> every worker.
  * `FORCE=true` (dispatch input or env)                -> every worker.
  * a `push`: deploy only workers whose own `cloudflare/<dir>/` tree changed;
    if the workflow file or the manifest itself changed, treat it as an infra
    change and deploy every worker (behaviour could have changed for all).

Outputs (written to $GITHUB_OUTPUT, GitHub/Forgejo-Actions compatible):
  * matrix : a JSON object `{"include": [ {name,dir,health_url}, ... ]}` suitable
             for `strategy.matrix: ${{ fromJSON(...) }}`.
  * any    : "true" if at least one worker will deploy, else "false" (lets the
             deploy job be skipped cleanly with no empty-matrix error).
  * count  : number of workers selected (for the human-readable summary).

Fails closed: if the changed-file set can't be determined for a push (shallow
clone, missing parent), it deploys nothing and prints a warning telling the
operator to re-run via manual dispatch — never a surprise deploy-everything.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Prefer the CI-provided checkout root (GITHUB_WORKSPACE) so the planner isn't
# coupled to this script's location; fall back to walking up from __file__ for
# local runs / when the env var is unset.
_WORKSPACE = os.environ.get("GITHUB_WORKSPACE")
REPO_ROOT = Path(_WORKSPACE) if _WORKSPACE else Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "cloudflare" / "deploy-manifest.json"
WORKFLOW_REL = ".forgejo/workflows/deploy-cloudflare.yml"
MANIFEST_REL = "cloudflare/deploy-manifest.json"


def _load_workers() -> list[dict]:
    data = json.loads(MANIFEST.read_text())
    workers = data.get("workers", [])
    # Only well-formed entries with a name + dir are deployable.
    return [w for w in workers if w.get("name") and w.get("dir")]


def _git_changed_files(before: str, after: str) -> list[str] | None:
    """Return the list of changed paths for a push, or None if undeterminable."""
    zero = {"", "0000000000000000000000000000000000000000"}
    candidates = []
    if before not in zero and after not in zero:
        candidates.append((f"{before}", f"{after}"))
    # Fallbacks for squash-merges / when the event range isn't usable.
    candidates.append(("HEAD~1", "HEAD"))
    for base, head in candidates:
        try:
            out = subprocess.run(
                ["git", "diff", "--name-only", f"{base}", f"{head}"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
            return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
        except subprocess.CalledProcessError:
            continue
    return None


def _emit(matrix: dict, any_selected: bool, count: int) -> None:
    out_path = os.environ.get("GITHUB_OUTPUT")
    lines = [
        f"matrix={json.dumps(matrix, separators=(',', ':'))}",
        f"any={'true' if any_selected else 'false'}",
        f"count={count}",
    ]
    if out_path:
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    # Always echo to the log for visibility.
    for line in lines:
        print(line)


def main() -> int:
    workers = _load_workers()
    by_key = {}
    for w in workers:
        by_key[w["name"]] = w
        by_key[w["dir"]] = w

    event = os.environ.get("GITHUB_EVENT_NAME", "")
    dispatch_worker = (os.environ.get("DISPATCH_WORKER") or "").strip()
    force = (os.environ.get("FORCE") or "").strip().lower() in ("1", "true", "yes")

    selected: list[dict]

    if event == "workflow_dispatch" and dispatch_worker and dispatch_worker != "all":
        target = by_key.get(dispatch_worker)
        if target is None:
            print(
                f"::error::Unknown worker '{dispatch_worker}'. "
                f"Valid: {', '.join(w['name'] for w in workers)}"
            )
            _emit({"include": []}, False, 0)
            return 1
        selected = [target]
    elif force or (event == "workflow_dispatch" and dispatch_worker in ("", "all")):
        selected = list(workers)
    else:
        # push: diff-driven selection
        changed = _git_changed_files(
            os.environ.get("GIT_BEFORE", ""), os.environ.get("GIT_AFTER", "")
        )
        if changed is None:
            print(
                "::warning::Could not determine changed files (shallow clone or "
                "missing parent commit). Deploying nothing — re-run via manual "
                "dispatch (workflow_dispatch) with the target worker if needed."
            )
            _emit({"include": []}, False, 0)
            return 0
        infra_changed = any(p in (WORKFLOW_REL, MANIFEST_REL) for p in changed)
        if infra_changed:
            print(
                "::notice::Deploy workflow or manifest changed — treating as an "
                "infra change and deploying all workers."
            )
            selected = list(workers)
        else:
            selected = [
                w
                for w in workers
                if any(p.startswith(f"cloudflare/{w['dir']}/") for p in changed)
            ]

    include = [
        {"name": w["name"], "dir": w["dir"], "health_url": w.get("health_url", "")}
        for w in selected
    ]
    if include:
        print(f"::notice::Deploy plan: {', '.join(w['name'] for w in include)}")
    else:
        print("::notice::No workers selected for deploy.")
    _emit({"include": include}, bool(include), len(include))
    return 0


if __name__ == "__main__":
    sys.exit(main())
