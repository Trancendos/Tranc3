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

Six ways this gate could have reported green without seeing anything
--------------------------------------------------------------------
Codex and CodeAnt found these on the first version, and each is real:

1. **A broken crate getting worse still passed.** The comparison read only
   `status`, so a crate already recorded `broken` could acquire new errors and
   neither branch fired -- on a gate whose stated purpose is making Rust
   dependency upgrades verifiable. The measured first error is now compared
   against the recorded one.
2. **The weekly run could not see the drift it exists for.** Every crate has a
   committed `Cargo.lock`, so plain `cargo check` reuses the locked graph and
   never resolves the newer releases a caret range allows. `--unlocked` copies
   the manifest and sources to a temporary directory WITHOUT the lock and
   compiles there -- which is also exactly what the `workers/nexus-ws-rs`,
   `vault-service-rs` and `rate-limit-service-rs` Dockerfiles do, since none of
   them copies `Cargo.lock` into the image.
3. **A cargo failure that was not a compile failure read as `broken`.** A
   registry outage, a missing toolchain or a timeout produced the same verdict
   as a type error, so an estate-wide network problem would have been recorded
   as "these crates do not compile". A run that could not compile now reports
   `blocked` and fails, because a gate that cannot see must not report what a
   healthy estate reports.
4. **An unknown, misspelled or null ledger status was accepted silently**, so a
   typo could disable regression checking while the gate said PASSED. The
   vocabulary is now closed and `broken` must carry a reason.
5. **Restoring `Cargo.lock` hid lockfile drift.** If a manifest change requires
   a lock update, cargo rewrites the lock, compiles against the new resolution,
   and the restore put the stale bytes back where `git diff --exit-code` could
   not see them. The rewrite is now reported as its own finding -- and the file
   is still restored, because the gate must not change what it measures.
6. **A crate nested under another crate's directory was dropped from
   discovery**, so the `[UNRECORDED]` protection passed without compiling it.
   Membership is now established with `cargo metadata` rather than assumed from
   directory nesting.

What is still not checked, said rather than implied
---------------------------------------------------
Each crate is compiled for the host target, plus any target the ledger records
for it (`wasm32-unknown-unknown` for the WASM crates). When a recorded target
is not installed the crate is reported `blocked`, never quietly passed on the
host alone.

Usage:
    python3 scripts/check_rust_crates.py
    python3 scripts/check_rust_crates.py --unlocked      # what the images build
    python3 scripts/check_rust_crates.py --write-ledger
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess  # noqa: S404 - invoking cargo is the entire point of this check
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "config" / "estate" / "rust_crate_status.yaml"

#: The closed status vocabulary. Anything else in the ledger is a defect in the
#: ledger, not an unknown state to shrug at.
OK, BROKEN, BLOCKED = "ok", "broken", "blocked"

#: Directories that never hold a crate worth compiling: build output, vendored
#: JavaScript, and git internals. `target/` matters most -- a built crate keeps
#: copies of its dependencies' manifests there, and walking into it would ask
#: this check to compile the whole of crates.io.
_SKIP = {"target", "node_modules", ".git", ".venv", "venv", "__pycache__"}

#: Cargo's own failures, as distinct from the compiler's. These mean the gate
#: could not see, which is a different report from "this does not compile".
_BLOCKED_MARKERS = (
    "failed to get",
    "failed to load source",
    "failed to download",
    "failed to fetch",
    "no matching package",
    "network failure",
    "certificate",
    "is not installed",
    "timed out",
)


@dataclass
class Measurement:
    """What one crate's compile actually showed."""

    status: str
    reason: str = ""
    lock_rewritten: bool = False
    targets: List[str] = field(default_factory=list)
    # Every diagnostic, not just the one shown. `reason` is what a human reads;
    # this is what the comparison asserts, because a crate that gains errors
    # while its first one holds still has got materially worse.
    diagnostics: List[str] = field(default_factory=list)


def _manifests() -> List[Path]:
    found = []
    for manifest in REPO.rglob("Cargo.toml"):
        if _SKIP & set(manifest.relative_to(REPO).parts):
            continue
        found.append(manifest)
    return sorted(found)


def _crate_roots() -> List[str]:
    """Every crate root, with membership established rather than assumed.

    Dropping any manifest that merely sits below another crate's directory is
    wrong: a crate placed there that the ancestor neither declares as a
    workspace member nor references as a path dependency gets no measurement
    and no ledger entry, so the [UNRECORDED] protection passes without ever
    compiling it. cargo metadata is asked which manifests each root covers.
    """
    covered: set = set()
    roots: List[Path] = []

    for manifest in _manifests():
        if manifest in covered:
            continue
        try:
            completed = subprocess.run(  # noqa: S603
                ["cargo", "metadata", "--no-deps", "--format-version", "1"],  # noqa: S607
                cwd=manifest.parent,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            roots.append(manifest.parent)
            continue
        if completed.returncode != 0:
            roots.append(manifest.parent)
            continue
        document = json.loads(completed.stdout)
        roots.append(Path(document["workspace_root"]))
        for package in document.get("packages", []):
            covered.add(Path(package["manifest_path"]))

    return sorted({root.relative_to(REPO).as_posix() for root in roots})


_ANSI = re.compile(r"\x1b\[[0-9;]*m")

# `file:line:col: error[CODE]` -- everything up to and including the code.
_ERROR_CODE = re.compile(r"error\[(E\d+)\]")
_TYPE_MISMATCH = re.compile(r"\bexpected `([^`]+)`, found `([^`]+)`")


def _normalise(line: str) -> str:
    """Strip the colour the workflow asks cargo for before comparing text.

    `rust.yml` sets `CARGO_TERM_COLOR: always`, so on CI every diagnostic
    arrives wrapped in SGR escapes while the ledger holds plain text. The two
    then differ on every run for a reason that has nothing to do with whether
    the crate compiles -- a gate that fails for a reason unrelated to what it
    measures is noise, and noise is what `|| true` gets attached to.
    """
    return _ANSI.sub("", line).strip()


def _identity(diagnostic) -> str:
    """One diagnostic's stable identity: its error code, and its types for E0308.

    Three things must all be true and they pull against each other.

    rustc rewords its own prose between releases -- the same unresolved
    `hyper::util` reads `failed to resolve: could not find util in hyper` on one
    toolchain and `cannot find util in hyper` on the next -- so the prose cannot
    be the assertion, or every rustc release fails this gate on nine crates at
    once for a reason unrelated to whether anything compiles.

    The location cannot be the assertion either. Keyed on `file:line:col`, a
    comment inserted above the first failing line of a recorded-broken crate
    trips [CHANGED] with character-identical error text, so every PR that so
    much as touches such a crate demands a ledger refresh.

    But the code alone is not enough: a crate can keep failing at the same place
    with a different type mismatch. E0308 therefore carries its operands, which
    are the compiler's own words for what actually differs.
    """
    if not isinstance(diagnostic, str):
        # A ledger `reason:` of the wrong type reached re.match here and raised
        # an unhandled TypeError, so the gate died with a traceback instead of
        # reporting the [LEDGER] finding that was waiting one function away.
        return repr(diagnostic)
    match = _ERROR_CODE.search(diagnostic)
    if not match:
        return diagnostic.strip()
    code = match.group(1)
    if code == "E0308":
        operands = _TYPE_MISMATCH.search(diagnostic)
        if operands:
            return f"E0308(expected={operands.group(1)}, found={operands.group(2)})"
    return code


def _fingerprint(diagnostics) -> List[str]:
    """Every diagnostic's identity, not just the first one's.

    Fingerprinting only the first error let a recorded-broken crate acquire new
    errors and still pass, because its first one had not moved -- a gate that
    reports a crate as unchanged while it gets materially worse. Sorted so the
    comparison does not depend on the order cargo happens to emit them, and a
    list rather than a set so gaining a second instance of the same error still
    registers.
    """
    if diagnostics is None:
        return []
    if isinstance(diagnostics, str):  # a ledger written before this field existed
        return [_identity(diagnostics)]
    if not isinstance(diagnostics, (list, tuple)):
        # A ledger `reason:`/`errors:` of the wrong type must surface as the
        # [LEDGER] finding waiting one function away, not as a TypeError
        # traceback from inside the comparison.
        return [_identity(diagnostics)]
    return sorted(_identity(d) for d in diagnostics)


def _classify(stderr: str, returncode: int) -> tuple:
    """A compile failure and a failure to compile at all are not the same thing."""
    # `--message-format short` prints a compiler diagnostic as
    # `src/main.rs:290:44: error[E0308]: ...` -- starting with the PATH, not
    # with "error". Filtering on startswith("error") alone therefore missed
    # every real diagnostic and left only cargo's "could not compile" summary,
    # which is the same line for every failure and so cannot tell one from
    # another. That would have defeated the [CHANGED] branch below on the day
    # it was added.
    diagnostics = [
        line
        for line in (_normalise(raw) for raw in stderr.splitlines())
        if line.startswith("error") or "error[" in line
    ]
    coded = [line for line in diagnostics if "error[" in line]
    if coded:
        return BROKEN, coded[0], coded
    for line in diagnostics:
        if any(marker in line.lower() for marker in _BLOCKED_MARKERS):
            return BLOCKED, line, [line]
    if diagnostics:
        return BROKEN, diagnostics[0], diagnostics
    return BLOCKED, f"cargo exited {returncode} with no diagnostic", []


def _run_check(root: Path, target: Optional[str]) -> tuple:
    command = ["cargo", "check", "--message-format", "short"]
    if target:
        command += ["--target", target]
    try:
        completed = subprocess.run(  # noqa: S603
            command, cwd=root, capture_output=True, text=True, timeout=1800, check=False
        )
    except FileNotFoundError:
        raise SystemExit("cargo is not installed, so this check cannot see anything") from None
    except subprocess.TimeoutExpired:
        return 1, "error: cargo check timed out after 1800s"
    return completed.returncode, completed.stderr


def _installed_targets() -> set:
    try:
        completed = subprocess.run(  # noqa: S603
            ["rustup", "target", "list", "--installed"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    return {line.strip() for line in completed.stdout.splitlines() if line.strip()}


def _measure_one(directory: str, *, unlocked: bool, targets: List[str]) -> Measurement:
    """Compile one crate on the host, and on any target the ledger records."""
    source = REPO / directory

    if targets:
        installed = _installed_targets()
        missing = [t for t in targets if t not in installed]
        if missing:
            return Measurement(
                BLOCKED,
                f"recorded target(s) {missing} are not installed, so this crate "
                f"was not checked for them",
                targets=targets,
            )

    if unlocked:
        # Exactly the Dockerfiles' inputs -- manifest and sources, no lock -- so
        # caret ranges resolve fresh. This is the only way a scheduled run can
        # see the dependency drift it was added for.
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch) / source.name
            shutil.copytree(
                source, work, ignore=shutil.ignore_patterns("target", "Cargo.lock", ".git")
            )
            for target in [None, *targets]:
                code, stderr = _run_check(work, target)
                if code != 0:
                    status, reason, diagnostics = _classify(stderr, code)
                    return Measurement(status, reason, targets=targets, diagnostics=diagnostics)
        return Measurement(OK, targets=targets)

    lock = source / "Cargo.lock"
    saved = lock.read_bytes() if lock.is_file() else None
    try:
        for target in [None, *targets]:
            code, stderr = _run_check(source, target)
            if code != 0:
                status, reason, diagnostics = _classify(stderr, code)
                rewritten = saved is not None and lock.is_file() and lock.read_bytes() != saved
                return Measurement(
                    status,
                    reason,
                    lock_rewritten=rewritten,
                    targets=targets,
                    diagnostics=diagnostics,
                )
        rewritten = saved is not None and lock.is_file() and lock.read_bytes() != saved
        return Measurement(OK, lock_rewritten=rewritten, targets=targets)
    finally:
        # A gate must not change the thing it measures.
        if saved is not None:
            lock.write_bytes(saved)
        elif lock.is_file():
            lock.unlink()


def _load_ledger() -> dict:
    if not LEDGER.is_file():
        return {}
    document = yaml.safe_load(LEDGER.read_text(encoding="utf-8")) or {}
    return document.get("crates") or {}


def _ledger_problems(ledger: dict) -> List[str]:
    """A malformed entry must not read as a satisfied one."""
    problems = []
    for directory, entry in sorted(ledger.items()):
        if not isinstance(entry, dict):
            problems.append(f"  [LEDGER] {directory}: entry is not a mapping")
            continue
        status = entry.get("status")
        if status not in (OK, BROKEN):
            problems.append(
                f"  [LEDGER] {directory}: status {status!r} is neither {OK!r} nor "
                f"{BROKEN!r}.\n        An unrecognised status silently disabled "
                f"regression checking\n        for this crate while the gate reported PASSED."
            )
        elif status == BROKEN and not str(entry.get("reason") or "").strip():
            problems.append(
                f"  [LEDGER] {directory}: recorded broken with no reason, so a new\n"
                f"        or worse failure here could never be distinguished from it."
            )
    return problems


def _as_entry(measurement: Measurement) -> dict:
    entry: dict = {"status": measurement.status}
    if measurement.reason:
        entry["reason"] = measurement.reason
    if measurement.targets:
        entry["targets"] = measurement.targets
    if measurement.diagnostics:
        entry["errors"] = _fingerprint(measurement.diagnostics)
    return entry


def _measure(*, unlocked: bool, ledger: dict) -> dict:
    measured = {}
    for directory in _crate_roots():
        entry = ledger.get(directory)
        targets = list(entry.get("targets") or []) if isinstance(entry, dict) else []
        measured[directory] = _measure_one(directory, unlocked=unlocked, targets=targets)
    return measured


def _compare(measured: dict, ledger: dict) -> List[str]:
    failures = _ledger_problems(ledger)

    for directory, result in sorted(measured.items()):
        recorded = ledger.get(directory)
        if recorded is None:
            failures.append(
                f"  [UNRECORDED] {directory}\n"
                f"        In the tree and not in the ledger, so nothing has decided\n"
                f"        whether it is expected to compile. Measured: {result.status}."
            )
            continue
        if not isinstance(recorded, dict) or recorded.get("status") not in (OK, BROKEN):
            continue  # already reported by _ledger_problems

        if result.status == BLOCKED:
            failures.append(
                f"  [BLOCKED] {directory}\n"
                f"        cargo could not compile this crate for a reason that is not\n"
                f"        the code, so this run saw nothing. Reported rather than\n"
                f"        recorded as broken: a gate that cannot see must not report\n"
                f"        what a healthy estate reports.\n        {result.reason}"
            )
        elif recorded["status"] == OK and result.status == BROKEN:
            failures.append(
                f"  [REGRESSED] {directory}\n"
                f"        Recorded as compiling; it no longer does.\n        {result.reason}"
            )
        elif recorded["status"] == BROKEN and result.status == OK:
            failures.append(
                f"  [FIXED, UNRECORDED] {directory}\n"
                f"        Recorded as broken; it now compiles. Refresh the ledger\n"
                f"        (--write-ledger) so the next regression cannot hide under\n"
                f"        a stale entry."
            )
        elif recorded["status"] == BROKEN and _fingerprint(
            result.diagnostics or result.reason
        ) != _fingerprint(recorded.get("errors") or recorded.get("reason")):
            failures.append(
                f"  [CHANGED] {directory}\n"
                f"        Still broken, but failing differently. Without this a crate\n"
                f"        already recorded broken could get materially worse and pass.\n"
                f"        recorded: {recorded.get('reason')}\n"
                f"        measured: {result.reason}"
            )

        if result.lock_rewritten:
            failures.append(
                f"  [LOCKFILE STALE] {directory}\n"
                f"        cargo rewrote Cargo.lock to compile, so the committed lock no\n"
                f"        longer matches the manifest. The lock was restored (this gate\n"
                f"        is read-only), which is exactly why the drift has to be\n"
                f"        reported here rather than left to `git diff` to notice."
            )

    for directory in sorted(set(ledger) - set(measured)):
        failures.append(f"  [GONE] {directory}\n        In the ledger, not in the tree.")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile every Rust crate in the tree.")
    parser.add_argument("--write-ledger", action="store_true", help="record what is measured")
    parser.add_argument(
        "--unlocked",
        action="store_true",
        help="resolve dependencies fresh, as the Dockerfiles and a caret range do",
    )
    args = parser.parse_args()

    ledger = _load_ledger()
    measured = _measure(unlocked=args.unlocked, ledger=ledger)
    mode = "unlocked (fresh resolution)" if args.unlocked else "locked (committed Cargo.lock)"

    if args.write_ledger:
        blocked = sorted(d for d, m in measured.items() if m.status == BLOCKED)
        if blocked:
            print(f"Refusing to record a run that could not compile: {blocked}")
            return 1
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        # Keep whatever preamble the committed ledger carries. The generated
        # header used to overwrite it, and the file's hand-written explanation
        # of why aeonmind/rust must NOT record a wasm target (pyo3-ffi's build
        # script needs an interpreter for the target) was the context a future
        # maintainer needs to not walk into an unfixable BLOCKED loop. The
        # gate's own failure text tells authors to run --write-ledger, so the
        # first fix would have destroyed it.
        preamble = ""
        if LEDGER.is_file():
            kept = []
            for line in LEDGER.read_text(encoding="utf-8").splitlines():
                if not line.startswith("#"):
                    break
                kept.append(line)
            if kept:
                preamble = "\n".join(kept) + "\n"
        if not preamble:
            preamble = (
                "# Generated by scripts/check_rust_crates.py --write-ledger.\n"
                "# Every Cargo crate in the tree, and whether it compiles. See the\n"
                "# script's docstring for why a crate may be recorded as broken.\n"
            )
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(
            preamble
            + yaml.safe_dump(
                {"crates": {d: _as_entry(m) for d, m in measured.items()}},
                sort_keys=True,
                default_flow_style=False,
            ),
            encoding="utf-8",
        )
        broken = sorted(d for d, m in measured.items() if m.status == BROKEN)
        print(f"Recorded {len(measured)} crates, {len(broken)} broken: {broken}")
        return 0

    failures = _compare(measured, ledger)
    if failures:
        print(f"Rust crate compile gate: FAILED — {mode}")
        print("\n".join(failures))
        return 1

    broken = sorted(d for d, m in measured.items() if m.status == BROKEN)
    print(
        f"Rust crate compile gate: PASSED — {mode}, {len(measured)} crates, "
        f"{len(measured) - len(broken)} compile, {len(broken)} recorded broken"
    )
    for directory in broken:
        print(f"  broken (recorded): {directory} — {ledger[directory].get('reason', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
