#!/usr/bin/env python3
"""Cloud-only go-live preflight — the counterpart to citadel_preflight.py.

`citadel_preflight.py` checks the self-hosted stack, which is blocked on hardware
funding. The cloud-only phase deploys a completely different surface — Fly.io apps,
Cloudflare Workers and Cloudflare Pages — and nothing checked that surface at all.
The result was that "are we ready to go live?" could only be answered for the path
that cannot currently be taken.

This validates every artifact the cloud-only deploy actually consumes, from a plain
checkout: no docker, no credentials, no network. It answers "would `deploy_cloud.py`
and the Cloudflare pipeline have what they need?" — not "is the platform healthy",
which is post_deploy_verify.py's job once endpoints exist.

Usage:
    python scripts/cloud_preflight.py           # human-readable report
    python scripts/cloud_preflight.py --json    # machine-readable
    python scripts/cloud_preflight.py --strict  # warnings become failures

Exit status: 0 when the cloud surface is deployable, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "cloudflare" / "deploy-manifest.json"
DEPLOY_CLOUD = ROOT / "scripts" / "deploy_cloud.py"

# Fly apps the cloud-only path deploys, and the directory each is deployed from.
FLY_APPS = {
    "tranc3-backend": ROOT / "fly.toml",
    "trancendos-bots": ROOT / "tranc3-bots" / "fly.toml",
}

# Secrets the operator must supply. These are never read or validated here — only
# their *names* are reported, so an operator knows what to set before deploying.
REQUIRED_CREDENTIALS = {
    "Fly.io": ["FLY_API_TOKEN"],
    "Fly app secrets (per app, set once)": [
        "SECRET_KEY",
        "JWT_SECRET",
        "DATABASE_URL",
        "REDIS_URL",
    ],
    "Cloudflare": ["CF_API_TOKEN", "CF_ACCOUNT_ID"],
}


@dataclass
class Result:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)

    def ok(self, msg: str) -> None:
        self.checks.append(msg)

    def fail(self, msg: str) -> None:
        self.failures.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _toml_value(text: str, key: str) -> str | None:
    """Minimal TOML scalar lookup — avoids a dependency for three keys."""
    m = re.search(rf'^\s*{re.escape(key)}\s*=\s*"([^"]*)"', text, re.MULTILINE)
    return m.group(1) if m else None


def check_fly(res: Result) -> None:
    for app, toml_path in FLY_APPS.items():
        rel = toml_path.relative_to(ROOT)
        if not toml_path.is_file():
            res.fail(f"Fly app '{app}': {rel} is missing — `fly deploy` has nothing to read")
            continue
        declared = _toml_value(toml_path.read_text(encoding="utf-8"), "app")
        if declared != app:
            res.fail(
                f"Fly app name mismatch: {rel} declares app = '{declared}', "
                f"but the deploy path targets '{app}'. Secrets and deploys would go to "
                f"different apps."
            )
        else:
            res.ok(f"Fly app '{app}' — {rel} declares a matching app name")

    # deploy_cloud.py's defaults must agree with fly.toml, or `--app` and the config
    # disagree and the deploy silently targets the wrong app.
    if DEPLOY_CLOUD.is_file():
        text = DEPLOY_CLOUD.read_text(encoding="utf-8")
        for var, expected in (
            ("FLY_BACKEND_APP", "tranc3-backend"),
            ("FLY_BOTS_APP", "trancendos-bots"),
        ):
            m = re.search(rf'{var}",\s*"([^"]+)"', text)
            if not m:
                res.warn(f"deploy_cloud.py: could not determine the {var} default")
            elif m.group(1) != expected:
                res.fail(
                    f"deploy_cloud.py defaults {var} to '{m.group(1)}', "
                    f"but fly.toml declares '{expected}'"
                )
            else:
                res.ok(f"deploy_cloud.py {var} default matches fly.toml ('{expected}')")
    else:
        res.fail("scripts/deploy_cloud.py is missing — the cloud deploy entry point")


def check_cloudflare_workers(res: Result) -> None:
    if not MANIFEST.is_file():
        res.fail("cloudflare/deploy-manifest.json is missing — the CF deploy plan source")
        return

    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        res.fail(f"cloudflare/deploy-manifest.json is not valid JSON: {exc}")
        return

    workers = manifest.get("workers") or []
    if not workers:
        res.fail("cloudflare/deploy-manifest.json lists no workers")
        return

    for entry in workers:
        name = entry.get("name", "<unnamed>")
        directory = ROOT / "cloudflare" / entry.get("dir", "")
        if not directory.is_dir():
            res.fail(f"CF worker '{name}': directory {directory.relative_to(ROOT)} does not exist")
            continue

        # DEPLOY.md states a worker must carry a committed lockfile because the
        # pipeline installs with lockfile-only `npm ci`. Nothing enforced it.
        for required in ("wrangler.toml", "package.json", "package-lock.json"):
            if not (directory / required).is_file():
                res.fail(
                    f"CF worker '{name}': missing {required}. "
                    f"The deploy runs `npm ci`, which fails without a committed lockfile."
                )

        wrangler = directory / "wrangler.toml"
        if wrangler.is_file():
            text = wrangler.read_text(encoding="utf-8")
            declared = _toml_value(text, "name")
            if declared != name:
                res.fail(
                    f"CF worker '{name}': wrangler.toml declares name = '{declared}'. "
                    f"`wrangler deploy` would publish to the wrong worker."
                )
            elif not _toml_value(text, "account_id"):
                res.warn(f"CF worker '{name}': wrangler.toml has no account_id")
            else:
                res.ok(f"CF worker '{name}' — wrangler.toml, package.json and lockfile present")


def check_frontend(res: Result) -> None:
    pages = ROOT / "cloudflare" / "pages" / "wrangler.toml"
    if not pages.is_file():
        res.warn("cloudflare/pages/wrangler.toml missing — no Pages config for the frontend")
        return

    text = pages.read_text(encoding="utf-8")
    out_dir = _toml_value(text, "pages_build_output_dir")
    if not out_dir:
        res.warn("cloudflare/pages/wrangler.toml declares no pages_build_output_dir")
        return

    # The path is relative to the wrangler.toml, and the build produces it — so its
    # absence in a fresh checkout is expected. Check the *source* exists instead.
    source = (pages.parent / out_dir).resolve()
    web_root = ROOT / "web"
    if not web_root.is_dir():
        res.fail(f"Pages output is {out_dir}, but {web_root.relative_to(ROOT)}/ does not exist")
    elif not (web_root / "package.json").is_file():
        res.fail("web/package.json missing — the frontend cannot be built for Pages")
    else:
        built = "built" if source.is_dir() else "not yet built"
        res.ok(f"Frontend — web/ present, Pages output {out_dir} ({built}; `npm run build` in web/)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Cloud-only go-live preflight")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = parser.parse_args()

    res = Result()
    check_fly(res)
    check_cloudflare_workers(res)
    check_frontend(res)

    failed = bool(res.failures) or (args.strict and bool(res.warnings))

    if args.json:
        print(
            json.dumps(
                {
                    "ok": not failed,
                    "checks": res.checks,
                    "warnings": res.warnings,
                    "failures": res.failures,
                    "required_credentials": REQUIRED_CREDENTIALS,
                },
                indent=2,
            )
        )
        return 1 if failed else 0

    print("Cloud-only go-live preflight")
    print("=" * 40)
    for line in res.checks:
        print(f"  OK    {line}")
    for line in res.warnings:
        print(f"  WARN  {line}")
    for line in res.failures:
        print(f"  FAIL  {line}")

    print()
    print("Operator-supplied credentials (names only — values are never read here):")
    for group, names in REQUIRED_CREDENTIALS.items():
        print(f"  {group}: {', '.join(names)}")

    print()
    if failed:
        print("BLOCKED — the cloud surface is not deployable as it stands.")
        return 1
    print(f"PASS — cloud surface is deployable ({len(res.checks)} checks, {len(res.warnings)} warnings).")
    print("Next: python scripts/deploy_cloud.py --gate-only, then deploy_cloud.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
