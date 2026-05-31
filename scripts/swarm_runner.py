#!/usr/bin/env python3
"""
Execute Trancendos swarm manifests (YAML task lists).

Zero-cost proactive automation — runs local scripts defined in config/swarm/manifests/.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


def load_manifest(path: Path) -> dict:
    text = path.read_text()
    if yaml is not None:
        return yaml.safe_load(text)
    # Minimal fallback without PyYAML
    raise RuntimeError("PyYAML required: pip install pyyaml")


def run_task(task: dict, root: Path) -> dict:
    script = task.get("script")
    if not script:
        return {"id": task.get("id"), "status": "skipped", "reason": "no script"}
    script_path = root / script
    if not script_path.is_file():
        return {"id": task.get("id"), "status": "failed", "reason": f"missing {script}"}
    args = [sys.executable, str(script_path)] + list(task.get("args") or [])
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(args, cwd=root, capture_output=True, text=True)
    return {
        "id": task.get("id"),
        "bot": task.get("bot"),
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-500:] if proc.stdout else "",
        "stderr_tail": proc.stderr[-500:] if proc.stderr else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run swarm manifest tasks")
    parser.add_argument(
        "--manifest",
        default="config/swarm/manifests/platform-health.yaml",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / args.manifest
    if not manifest_path.is_file():
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    manifest = load_manifest(manifest_path)
    results = []
    for task in manifest.get("tasks") or []:
        if args.dry_run:
            print(f"would run: {task.get('id')} -> {task.get('script')}")
            continue
        results.append(run_task(task, root))

    report = {
        "manifest": str(manifest_path),
        "orchestrator": manifest.get("orchestrator"),
        "run_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    out = root / "logs" / "proactive-health.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    failed = sum(1 for r in results if r.get("status") == "failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
