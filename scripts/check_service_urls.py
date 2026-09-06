#!/usr/bin/env python3
"""Cross-service URL validation — catches silently-failing service calls.

Imaginarium fanned a creative brief out to five Locations via
`http://localhost:<port>` defaults, and every one was wrong twice over:

  * wrong host — inside a container `localhost` is *that container*, so a
    localhost URL can never reach a sibling service whatever port it names
  * wrong port — 8051=hive-service, 8057=the-dutchy, 8065=observatory,
    8066=lab-service, 8067=library-service, none of them the intended target

Compose overrode none of the five, so the defaults were what ran. The failure
mode is the dangerous kind: the call raises, the error is captured into a
results blob, and the job is marked `completed`. It looks like it worked.

WHAT THIS FLAGS

A worker declares `os.getenv("X_URL", "http://localhost:<port>")` where a
compose service owns that port, AND compose does not set `X_URL` for the
declaring service. Both conditions matter:

  * if no compose service owns the port, the target is plausibly external —
    a host-run ComfyUI, AUTOMATIC1111 or Tabby instance — and localhost is a
    legitimate default, so it is reported as INFO, not failed
  * if compose *does* set the var, the default is dead code and cannot affect
    production, so it is reported as INFO

That leaves exactly the cases where a container would try to call itself in
production. The estate's convention for the fix is already established:
`http://<compose-service>:<port>`, used by 26 vars in
docker-compose.production.yml.

Exit 0 when no live cross-service localhost call remains, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.production.yml"

URL_DEFAULT = re.compile(
    r'os\.getenv\(\s*["\'](\w*_URL)["\']\s*,\s*["\']http://(?:localhost|127\.0\.0\.1):(\d+)'
)

# Vars whose target genuinely does not run in docker-compose.production.yml, so
# the compose service that happens to own the port is a coincidence rather than
# the intended callee. Rewriting these to service-name DNS would point them at
# the wrong thing — worse than leaving them. Each needs a real address supplied
# at deploy time; the reason is recorded so the exemption stays reviewable, and
# anything NOT listed here still fails the build.
KNOWN_EXTERNAL = {
    "PENPOT_URL": (
        "Penpot is a planned Fabulousa integration and is not a service in this "
        "stack; :9001 collides with minio by coincidence"
    ),
    "GITEA_URL": (
        "The Workshop runs Forgejo from deploy/forgejo/docker-compose.yml on "
        "127.0.0.1:3456, a separate stack; :3000 collides with gotenberg by "
        "coincidence"
    ),
    "OBSERVATORY_URL": (
        "workers/optional-services-health is not a docker-compose.production.yml "
        "service, so it has no environment block to pin — it runs ad hoc"
    ),
}


def parse_compose() -> tuple[dict[str, str], dict[str, set[str]]]:
    """Return (port -> owning service, service -> env var names it sets)."""
    port_owner: dict[str, str] = {}
    env_set: dict[str, set[str]] = defaultdict(set)
    current = None
    for line in COMPOSE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^  ([a-z0-9][a-z0-9_-]*):\s*$", line)
        if m:
            current = m.group(1)
            continue
        if not current:
            continue
        pm = re.search(r'^\s+- "(\d+):(\d+)"', line)
        if pm:
            port_owner.setdefault(pm.group(1), current)
        pe = re.search(r"^\s+- PORT=(\d+)", line)
        if pe:
            port_owner.setdefault(pe.group(1), current)
        ev = re.search(r"^\s+- ([A-Z][A-Z0-9_]*)=", line)
        if ev:
            env_set[current].add(ev.group(1))
    return port_owner, env_set


def owning_service(path: Path) -> str:
    """Compose service name for the file that declares the default.

    `src/` is not a worker — it is the backend package that `api.py` imports, so
    it runs inside the `tranc3-backend` container. Mapping it there matters: the
    first version of this check left `src/` unattributed and so could not see
    that compose already sets OLLAMA_URL for tranc3-backend, and reported six
    dead-code defaults as production failures. A check that cries wolf gets
    switched off, which is worse than not having it.
    """
    parts = path.relative_to(ROOT).parts
    if parts[0] == "workers" and len(parts) > 1:
        return parts[1]
    if parts[0] == "src":
        return "tranc3-backend"
    return ""


def main() -> int:
    port_owner, env_set = parse_compose()

    errors: list[str] = []
    info: list[str] = []
    scanned = 0

    files = [
        p
        for p in list(ROOT.glob("workers/**/*.py")) + list(ROOT.glob("src/**/*.py"))
        if "__pycache__" not in str(p)
    ]
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in URL_DEFAULT.finditer(text):
            var, port = m.group(1), m.group(2)
            scanned += 1
            rel = f.relative_to(ROOT)
            target = port_owner.get(port)
            declarer = owning_service(f)

            if var in KNOWN_EXTERNAL:
                info.append(f"{rel}: {var} exempt — {KNOWN_EXTERNAL[var]}")
                continue
            if not target:
                info.append(
                    f"{rel}: {var} → localhost:{port} — no compose service owns this "
                    f"port, so an external/host-run target is plausible"
                )
                continue
            if declarer and var in env_set.get(declarer, set()):
                info.append(
                    f"{rel}: {var} default is localhost:{port} but compose sets {var} "
                    f"for `{declarer}` — default is dead code"
                )
                continue
            if declarer and target == declarer:
                info.append(f"{rel}: {var} → localhost:{port} is `{declarer}` itself — in-process")
                continue
            errors.append(
                f"{rel}: {var} defaults to localhost:{port}, which belongs to compose "
                f"service `{target}`"
                + (f", and compose does not set {var} for `{declarer}`" if declarer else "")
                + f". A container cannot reach `{target}` via localhost — use "
                f"http://{target}:{port}"
            )

    for line in info:
        print(f"[INFO]  {line}")
    for line in errors:
        print(f"[ERROR] {line}", file=sys.stderr)

    print(
        f"\nservice-url check: {scanned} URL default(s) across {len(files)} file(s), "
        f"{len(info)} informational, {len(errors)} error(s)"
    )
    if errors:
        print("Service URL check: FAILED", file=sys.stderr)
        return 1
    print("Service URL check: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
