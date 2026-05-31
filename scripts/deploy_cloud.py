#!/usr/bin/env python3
"""
CLOUD_ONLY deploy — Fly.io backend + bots (no Citadel Docker).

Requires:
  FLY_API_TOKEN  — from https://fly.io/user/personal_access_tokens
  Fly app secrets already set (SECRET_KEY, JWT_SECRET, DATABASE_URL, REDIS_URL)

Usage:
  export FLY_API_TOKEN=...
  python scripts/deploy_cloud.py
  python scripts/deploy_cloud.py --gate-only
  python scripts/deploy_cloud.py --backend-only
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_APP = os.environ.get("FLY_BACKEND_APP", "tranc3-backend")
BOTS_APP = os.environ.get("FLY_BOTS_APP", "trancendos-bots")
BACKEND_HEALTH = f"https://{BACKEND_APP}.fly.dev/health"
BOTS_HEALTH = f"https://{BOTS_APP}.fly.dev/health"


def _log(msg: str) -> None:
    print(msg, flush=True)


def _run(cmd: list[str], *, check: bool = True, cwd: Path | None = None) -> int:
    _log(f"  $ {' '.join(cmd)}")
    env = {**os.environ, "FLY_API_TOKEN": os.environ.get("FLY_API_TOKEN", "")}
    r = subprocess.run(cmd, cwd=cwd or ROOT, env=env)
    if check and r.returncode != 0:
        raise SystemExit(r.returncode)
    return r.returncode


def _fly() -> str:
    fly = shutil.which("flyctl") or shutil.which("fly")
    if fly:
        return fly
    home = Path.home() / ".fly" / "bin" / "flyctl"
    if home.is_file():
        return str(home)
    _log("Installing flyctl...")
    _run(["bash", "-c", "curl -L https://fly.io/install.sh | sh"], check=False)
    if home.is_file():
        return str(home)
    raise SystemExit(
        "flyctl not found. Install: https://fly.io/docs/hands-on/install-flyctl/"
    )


def _http_ok(url: str, timeout: float = 90.0) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout
    last_err = ""
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read(200).decode("utf-8", errors="replace")
                if resp.status == 200:
                    return True, body[:200]
                last_err = f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
        except Exception as e:
            last_err = str(e)
        time.sleep(5)
    return False, last_err


def _gate() -> None:
    _log("==> Pre-deploy quality gate")
    _run([sys.executable, "scripts/pre_deploy_quality_gate.py"])


def _deploy_app(fly: str, app: str, *, cwd: Path) -> None:
    _log(f"==> Deploy {app}")
    _run([fly, "deploy", "--remote-only", "--app", app], cwd=cwd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Tranc3 CLOUD_ONLY Fly deploy")
    parser.add_argument("--gate-only", action="store_true")
    parser.add_argument("--backend-only", action="store_true")
    parser.add_argument("--skip-health", action="store_true")
    args = parser.parse_args()

    _log(f"Tranc3 cloud deploy — mode CLOUD_ONLY — root: {ROOT}")
    _gate()

    if args.gate_only:
        _log("Gate-only complete (PASS).")
        return 0

    token = os.environ.get("FLY_API_TOKEN", "").strip()
    if not token:
        _log("")
        _log("ERROR: FLY_API_TOKEN is not set — cannot deploy from this environment.")
        _log("")
        _log("On your machine (with Fly org access):")
        _log("  set FLY_API_TOKEN=your_token          # Windows CMD")
        _log("  export FLY_API_TOKEN=your_token       # bash")
        _log("  python scripts/deploy_cloud.py")
        _log("")
        _log("Or trigger Forgejo workflow: Deploy to Fly.io (The Workshop)")
        _log("  Needs org secrets: FLY_API_TOKEN, SECRET_KEY, DATABASE_URL, REDIS_URL, ...")
        _log("")
        _log("Set Fly secrets once (example):")
        _log(f"  fly secrets set SECRET_KEY=... JWT_SECRET=... DATABASE_URL=... REDIS_URL=... --app {BACKEND_APP}")
        return 1

    fly = _fly()
    _run([fly, "auth", "whoami"], check=False)

    _deploy_app(fly, BACKEND_APP, cwd=ROOT)
    if not args.backend_only:
        bots_dir = ROOT / "tranc3-bots"
        if (bots_dir / "fly.toml").is_file():
            _deploy_app(fly, BOTS_APP, cwd=bots_dir)
        else:
            _log("WARN: tranc3-bots/fly.toml missing — skipping bots deploy")

    if args.skip_health:
        return 0

    _log("==> Wait for Fly health (cold start may take ~60s)")
    ok, detail = _http_ok(BACKEND_HEALTH)
    if ok:
        _log(f"  OK {BACKEND_HEALTH} — {detail}")
    else:
        _log(f"  WARN backend health: {detail} — check: fly logs --app {BACKEND_APP}")

    if not args.backend_only:
        ok_b, detail_b = _http_ok(BOTS_HEALTH, timeout=60)
        if ok_b:
            _log(f"  OK {BOTS_HEALTH}")
        else:
            _log(f"  WARN bots health: {detail_b}")

    _log("")
    _log("Cloud deploy finished.")
    _log(f"  API:  {BACKEND_HEALTH}")
    _log(f"  Bots: {BOTS_HEALTH}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
