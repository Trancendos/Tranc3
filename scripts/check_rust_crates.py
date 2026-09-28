#!/usr/bin/env python3
"""Compile every Rust crate in the tree, and refuse to let one go unwatched.

The failure this exists for
---------------------------
`.github/workflows/rust.yml` is named in `CLAUDE.md` as one of the workflows
that gate this repository's pull requests. It does gate one thing. It is
filtered to `paths: aeonmind/rust/**` and every job sets
`working-directory: aeonmind/rust`, so it compiles exactly one of the tree's
**nine** Cargo crates. The other eight have no compile check anywhere --
not in `.github/`, not in `.forgejo/`, not in a Dockerfile that anything runs
in CI. A pull request that touches only `rust_extensions/**` does not even
trigger the workflow, so it goes green without one rustc invocation.

Measured on 2026-09-28, with `cargo check` on each crate in turn:

  ok       aeonmind/rust
  ok       aeonmind/wasm
  ok       rust_extensions/tranc3_snn
  ok       src/nanoservices/rust/tranc3-nanoservice
  ok       workers/rate-limit-service-rs
  ok       workers/vault-service-rs
  BROKEN   rust_extensions/tranc3_crypto          16 errors
  BROKEN   src/nanoservices/nsa_broker             6 errors
  BROKEN   workers/nexus-ws-rs                     9 errors

The three are the same shape: a caret version range let a dependency move
to an API the source was never updated for, and nothing compiled it.
`tranc3_crypto` -- 15 pyo3 0.29 errors (`PyBytes::new_bound` gone, `PyObject`
unresolved, an ambiguous `wrap`) and one `aes_gcm::aead::OsRng` that aes-gcm
0.11 no longer re-exports. `nsa_broker` -- `hyper::util` moved out to
`hyper-util` in hyper 1.x, plus two assignments through a `&` borrow that no
dependency caused. `nexus-ws-rs` -- axum 0.8's `Message::Text` takes
`Utf8Bytes`, the source passes `String`, nine times.

Three of nine do not compile, and all three are live rather than dead:

  * `workers/nexus-ws-rs` has a Dockerfile and a `docker-compose.production.yml`
    service. Its Dockerfile copies `Cargo.toml` and `src` and NOT `Cargo.lock`,
    so the image resolves dependencies fresh on every build. Reproducing that
    exactly -- manifest and sources only, no lockfile -- fails with the same
    nine `expected Utf8Bytes, found String` errors: `axum` 0.8's WebSocket
    `Message::Text` takes `Utf8Bytes`, and the source passes `String`. The
    container cannot be built today.
  * `src/nanoservices/nsa_broker` is described by `src/nanoservices/__init__.py`
    as the shared-memory IPC broker on port 7780 and is registered in the
    semver enforcer and the API-versioning registry.
  * `rust_extensions/tranc3_crypto` is the "memory-safe, constant-time
    AES-256-GCM" extension behind `src/security/rust_crypto.py`, which catches
    the import error and falls back to Python `cryptography` with a debug log.
    That fallback is why nobody noticed: a component that cannot be built reads
    as merely not installed.

This is the estate's recurring defect in a language the estate's gates do not
speak. A check scoped so narrowly that it cannot fail for eight of nine
subjects reports the same green as a check that examined all nine.

It is also the answer to the open Rust dependency-bot pull requests -- the
RustCrypto family (#1098, #1099, #1102, #1106), `#1088` uuid, `#1065` serde,
`#1058` async-trait. Every one of them proposes an upgrade to a crate that
nothing compiles, so merging any of them is unverifiable by construction. A
dependency bot is only as good as the build it feeds.

Why a ledger rather than a rule
-------------------------------
Failing CI on all three today would put the build red for three separate
migrations nobody has been asked to do, which teaches people to wave the gate
through. So the measured status of every crate is recorded in
`config/estate/rust_crate_status.yaml`, and this fails on:

  * a crate the ledger calls `ok` that no longer compiles,
  * a crate the ledger calls `broken` that now compiles -- the ledger is stale
    and the fix must be recorded, or the next regression slips in under it,
  * a crate the ledger does not mention at all, so a new crate cannot be added
    without deciding which of the two it is.

The third is the one that makes this different from the workflow it replaces:
a crate added tomorrow is covered tomorrow, without anyone remembering to add
a job for it.

Usage:
    python3 scripts/check_rust_crates.py
    python3 scripts/check_rust_crates.py --write-ledger
"""

from __future__ import annotations

import argparse
import subprocess  # noqa: S404 - invoking cargo is the entire point of this check
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "config" / "estate" / "rust_crate_status.yaml"

#: Directories that never hold a crate worth compiling: build output, vendored
#: JavaScript, and git internals. `target/` matters most -- a built crate keeps
#: copies of its dependencies' manifests there, and walking into it would ask
#: this check to compile the whole of crates.io.
_SKIP = {"target", "node_modules", ".git", ".venv", "venv", "__pycache__"}


def _crate_dirs() -> list[str]:
    """Every crate root in the tree, as repo-relative posix paths.

    A crate root is a directory holding a `Cargo.toml` that is not itself
    inside another crate's sources. Nested manifests are left out rather than
    compiled twice: cargo builds a workspace or a path dependency from its
    root, so checking the root already covers them.
    """
    found: list[Path] = []
    for manifest in REPO.rglob("Cargo.toml"):
        relative = manifest.relative_to(REPO)
        if _SKIP & set(relative.parts):
            continue
        found.append(manifest.parent)

    roots: list[Path] = []
    for candidate in sorted(found):
        if any(candidate != other and other in candidate.parents for other in found):
            continue
        roots.append(candidate)
    return [path.relative_to(REPO).as_posix() for path in roots]


def _compile(directory: str) -> tuple[bool, str]:
    """Run `cargo check` in one crate. Returns (compiled, first error line).

    `--message-format short` keeps the recorded reason to one line, which is
    what a ledger entry can carry without going stale on every rustc release
    that rewords a note.
    """
    root = REPO / directory
    lock = root / "Cargo.lock"
    # A gate must not change the thing it measures. `cargo check` rewrites
    # Cargo.lock whenever a transitive dependency has a newer compatible
    # release, which would leave the working tree dirty after a run that is
    # supposed to be read-only. `--locked` is not the answer: it would fail a
    # crate for lockfile drift and report that as a compile failure, which is
    # a different defect wearing this one's error message.
    saved = lock.read_bytes() if lock.is_file() else None

    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["cargo", "check", "--message-format", "short"],  # noqa: S607
            cwd=root,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
    except FileNotFoundError:
        raise SystemExit("cargo is not installed, so this check cannot see anything") from None
    except subprocess.TimeoutExpired:
        return False, "cargo check timed out after 1800s"
    finally:
        if saved is not None:
            lock.write_bytes(saved)
        elif lock.is_file():
            lock.unlink()

    if completed.returncode == 0:
        return True, ""

    for line in completed.stderr.splitlines():
        if "error[" in line or line.startswith("error"):
            return False, line.strip()
    return False, f"cargo check exited {completed.returncode} with no error line"


def _measure() -> dict[str, dict[str, str]]:
    """Compile every crate and return its measured status, keyed by directory."""
    measured: dict[str, dict[str, str]] = {}
    for directory in _crate_dirs():
        compiled, reason = _compile(directory)
        measured[directory] = (
            {"status": "ok"} if compiled else {"status": "broken", "reason": reason}
        )
    return measured


def _load_ledger() -> dict[str, dict[str, str]]:
    if not LEDGER.is_file():
        return {}
    document = yaml.safe_load(LEDGER.read_text(encoding="utf-8")) or {}
    return document.get("crates") or {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-ledger", action="store_true", help="record the measured status of every crate"
    )
    args = parser.parse_args()

    measured = _measure()

    if args.write_ledger:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(
            "# Generated by scripts/check_rust_crates.py --write-ledger.\n"
            "# Every Cargo crate in the tree, and whether it compiles. See the\n"
            "# script's docstring for why a crate may be recorded as broken.\n"
            + yaml.safe_dump({"crates": measured}, sort_keys=True, default_flow_style=False),
            encoding="utf-8",
        )
        broken = sorted(k for k, v in measured.items() if v["status"] == "broken")
        print(f"Recorded {len(measured)} crates, {len(broken)} broken: {broken}")
        return 0

    ledger = _load_ledger()
    failures: list[str] = []

    for directory, result in sorted(measured.items()):
        recorded = ledger.get(directory)
        if recorded is None:
            failures.append(
                f"  [UNRECORDED] {directory}\n"
                f"        This crate is in the tree and not in the ledger, so nothing\n"
                f"        has decided whether it is expected to compile. It currently\n"
                f"        {'compiles' if result['status'] == 'ok' else 'does NOT compile'}."
            )
            continue
        if recorded.get("status") == "ok" and result["status"] == "broken":
            failures.append(
                f"  [REGRESSED] {directory}\n"
                f"        Recorded as compiling; it no longer does.\n"
                f"        {result['reason']}"
            )
        elif recorded.get("status") == "broken" and result["status"] == "ok":
            failures.append(
                f"  [FIXED, UNRECORDED] {directory}\n"
                f"        Recorded as broken; it now compiles. Refresh the ledger\n"
                f"        (--write-ledger) so the next regression cannot hide under\n"
                f"        a stale entry."
            )

    for directory in sorted(set(ledger) - set(measured)):
        failures.append(
            f"  [GONE] {directory}\n        In the ledger, not in the tree. Remove the entry."
        )

    if failures:
        print("Rust crate compile gate: FAILED")
        print("\n".join(failures))
        return 1

    broken = sorted(k for k, v in measured.items() if v["status"] == "broken")
    print(
        f"Rust crate compile gate: PASSED — {len(measured)} crates, "
        f"{len(measured) - len(broken)} compile, {len(broken)} recorded broken"
    )
    for directory in broken:
        print(f"  broken (recorded): {directory} — {ledger[directory].get('reason', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
