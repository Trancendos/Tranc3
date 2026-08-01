#!/usr/bin/env python3
"""Post-deploy smoke check for the cloud-only stack.

Verifies the *live* deployment — not the checkout — after every deploy and
every rollout-stage change. Stdlib only, no credentials needed: everything it
checks is the unauthenticated surface a new tester would hit first.

Checks:
  1. Backend /health responds 200 with a healthy/degraded status body.
  2. Backend /ready responds (200 ready, 503 still booting — reported, not fatal).
  3. The registration gate matches the expected rollout stage:
       gated stages  -> a probe registration is refused with 403 + stage name
       public        -> the probe is *not* 403'd (it fails 400 on password
                        strength instead, so the probe never creates an account)
  4. Optional: gateway and frontend URLs answer at all.

Usage:
  python scripts/cloud_smoke_check.py --expect-stage owner
  python scripts/cloud_smoke_check.py \
      --backend-url https://tranc3-backend.fly.dev \
      --gateway-url https://api.trancendos.com \
      --frontend-url https://trancendos.com \
      --expect-stage private_beta --json

Exit codes: 0 all checks pass, 1 any check fails, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

DEFAULT_BACKEND = "https://tranc3-backend.fly.dev"
GATED_STAGES = {"owner", "private_beta", "extended_beta"}
KNOWN_STAGES = GATED_STAGES | {"public"}
TIMEOUT = 15

# The probe deliberately uses a password that fails the backend's strength
# validation: in public stage the request dies with 400 *after* the rollout
# gate, proving the gate is open without ever creating an account.
PROBE_BODY = {"username": "", "password": "x", "invite_code": "smoke-probe-invalid"}


def _request(url: str, method: str = "GET", body: dict | None = None) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(  # noqa: S310 — https URLs supplied by operator
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "User-Agent": "cloud-smoke-check"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310
            return resp.status, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:  # URLError, timeout, TLS
        return 0, f"{type(e).__name__}: {e}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--backend-url", default=DEFAULT_BACKEND)
    ap.add_argument("--gateway-url", default=None, help="optional, e.g. https://api.trancendos.com")
    ap.add_argument("--frontend-url", default=None)
    ap.add_argument("--expect-stage", choices=sorted(KNOWN_STAGES), default=None)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    backend = args.backend_url.rstrip("/")
    checks: list[dict] = []

    def record(name: str, ok: bool, detail: str, fatal: bool = True) -> None:
        checks.append({"check": name, "ok": ok, "fatal": fatal, "detail": detail})

    # 1. /health
    status, body = _request(f"{backend}/health")
    if status == 200:
        try:
            health = json.loads(body).get("status", "?")
        except json.JSONDecodeError:
            health = "unparseable"
        record("backend_health", health in ("healthy", "degraded"), f"200, status={health}")
    else:
        record("backend_health", False, f"HTTP {status}: {body[:200]}")

    # 2. /ready — informational: 503 during model bootstrap is expected
    status, _ = _request(f"{backend}/ready")
    record("backend_ready", status in (200, 503), f"HTTP {status}", fatal=False)

    # 3. Rollout gate probe
    if args.expect_stage:
        body_probe = dict(PROBE_BODY)
        body_probe["username"] = f"smoke-probe-{int(time.time())}"
        status, body = _request(f"{backend}/auth/register", "POST", body_probe)
        if args.expect_stage in GATED_STAGES:
            if status == 403 and args.expect_stage in body:
                record("rollout_gate", True, f"403 naming stage '{args.expect_stage}'")
            elif status == 400:
                # The probe cleared the gate (spare capacity, no invite code
                # configured) and died on password validation. Registration is
                # genuinely possible, so the stage cannot be confirmed from
                # outside — set ROLLOUT_INVITE_CODE for a verifiable gate.
                record(
                    "rollout_gate",
                    False,
                    "gate open with capacity remaining — set ROLLOUT_INVITE_CODE "
                    "to make the stage externally verifiable",
                    fatal=False,
                )
            else:
                record(
                    "rollout_gate",
                    False,
                    f"HTTP {status} (want 403 naming '{args.expect_stage}', or 400): {body[:200]}",
                )
        else:  # public: gate must NOT refuse; probe then fails password strength
            record(
                "rollout_gate",
                status != 403,
                f"HTTP {status} (any non-403 means the gate is open): {body[:200]}",
            )

    # 4. Optional surfaces — reachability only
    for name, url in (("gateway", args.gateway_url), ("frontend", args.frontend_url)):
        if url:
            status, body = _request(url)
            record(name, status not in (0,), f"HTTP {status or body[:120]}", fatal=False)

    failed = [c for c in checks if not c["ok"] and c["fatal"]]
    warned = [c for c in checks if not c["ok"] and not c["fatal"]]

    if args.as_json:
        print(json.dumps({"ok": not failed, "checks": checks}, indent=2))
    else:
        for c in checks:
            mark = "OK  " if c["ok"] else ("WARN" if not c["fatal"] else "FAIL")
            print(f"{mark} {c['check']}: {c['detail']}")
        print()
        if failed:
            print(f"Smoke check FAILED — {len(failed)} failing check(s)")
        else:
            print("Smoke check PASSED" + (f" ({len(warned)} warning(s))" if warned else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
