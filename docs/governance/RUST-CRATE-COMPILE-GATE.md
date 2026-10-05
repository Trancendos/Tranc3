# The Rust Crate Compile Gate

**Owner:** The Workshop (Larry Lowhammer) · **Measured:** 2026-09-28 ·
**Code:** `scripts/check_rust_crates.py`, `config/estate/rust_crate_status.yaml`,
`.github/workflows/rust.yml` (job `crates`)

---

## 1. What was measured

`cargo check`, run once in each of the nine Cargo crates in this tree:

| Crate | Result |
|---|---|
| `aeonmind/rust` | compiles |
| `aeonmind/wasm` | compiles |
| `rust_extensions/tranc3_snn` | compiles |
| `src/nanoservices/rust/tranc3-nanoservice` | compiles |
| `workers/rate-limit-service-rs` | compiles |
| `workers/vault-service-rs` | compiles |
| **`rust_extensions/tranc3_crypto`** | **16 errors** |
| **`src/nanoservices/nsa_broker`** | **6 errors** |
| **`workers/nexus-ws-rs`** | **9 errors** |

Three of nine do not compile.

## 2. Why nobody knew

`.github/workflows/rust.yml` was filtered to `paths: aeonmind/rust/**`, and all
three of its jobs set `working-directory: aeonmind/rust`. It compiled **one**
crate. The path filter meant a pull request touching only `rust_extensions/`,
`workers/*-rs/` or `src/nanoservices/` did not trigger the workflow at all — so
eight of nine crates went green without a single rustc invocation, on a
workflow `CLAUDE.md` names as one of the checks gating this repository's pull
requests.

This is the estate's recurring defect in a language its gates did not speak. A
check scoped so narrowly that it cannot fail for eight of nine subjects reports
the same green as a check that examined all nine.

## 3. The three, and why each matters

All three are the same shape — a caret version range let a dependency move to
an API the source was never updated for — and none of them is dead code.

**`workers/nexus-ws-rs`** has a `Dockerfile` and a service in
`docker-compose.production.yml`. Nine errors, all `expected Utf8Bytes, found
String`: axum 0.8's WebSocket `Message::Text` takes `Utf8Bytes` and the source
passes `String`.

Its Dockerfile copies `Cargo.toml` and `src` and **not** `Cargo.lock`, so the
image resolves dependencies fresh on every build. Reproducing that exactly —
manifest and sources only, no lockfile, in a clean directory — fails with the
same nine errors. **The container cannot be built today.** That is not an
inference from the local check; it is the Dockerfile's own inputs, run.

**`src/nanoservices/nsa_broker`** is described by `src/nanoservices/__init__.py`
as the shared-memory IPC broker on port 7780, and is registered in
`src/nanoservices/semver_enforcer/` and `src/nanoservices/api_versioning/`. Six
errors: `hyper::util` moved out to the separate `hyper-util` crate in hyper
1.x, plus two assignments through a `&` borrow that no dependency caused —
those were never compiled by anyone.

**`rust_extensions/tranc3_crypto`** is the "memory-safe, constant-time
AES-256-GCM cryptographic nanoservice" behind `src/security/rust_crypto.py`.
Fifteen pyo3 0.29 errors (`PyBytes::new_bound` gone, `PyObject` unresolved, an
ambiguous `wrap`) and one `aes_gcm::aead::OsRng` that aes-gcm 0.11 no longer
re-exports.

The shim catches the import error and falls back to Python `cryptography` with
an **info-level** log line. That fallback is why nobody noticed: a component
that cannot be built reads as merely not installed. It is the same pattern as a
sensor that reports clean because it cannot see — `docs/governance/IMMUNE-SYSTEM.md`
names it, and this is an instance of it in the crypto path.

## 4. What this means for the Rust dependency-bot pull requests

Seven open bot pull requests propose Rust upgrades: the RustCrypto family
(#1098 hkdf, #1099 hmac, #1102 pbkdf2, #1106 sha2), #1088 uuid, #1065 serde and
#1058 async-trait. Every one of them targets a crate that nothing compiles, so
merging any of them is unverifiable by construction.

The four RustCrypto ones share a further constraint that is worth stating
before anyone merges one alone: `rust_extensions/tranc3_crypto` declares
`pbkdf2 0.12`, `sha2 0.10`, `hmac 0.12` and `hkdf 0.12` together, and the
proposed versions cross the RustCrypto `digest` 0.10 → 0.11 boundary. They move
as a set or not at all.

A dependency bot is only as good as the build it feeds. The gate comes first.

## 5. The gate

`scripts/check_rust_crates.py` discovers every crate root in the tree —
excluding `target/` and `node_modules/`, and excluding a nested manifest only
when `cargo metadata` shows another root already covers it as a workspace
member (the membership check described below) — compiles each, and compares
the result against `config/estate/rust_crate_status.yaml`. It fails on:

- a crate recorded `ok` that no longer compiles,
- a crate recorded `broken` that now compiles, so a fix cannot land without
  refreshing the ledger and the next regression cannot hide under a stale entry,
- a crate in the tree the ledger does not mention, so a crate added tomorrow is
  covered tomorrow rather than when someone remembers to add a job for it,
- a crate in the ledger that is no longer in the tree.

It restores each `Cargo.lock` it touches: `cargo check` rewrites the lock
whenever a transitive dependency has a newer compatible release, and a gate
must not change the thing it measures. The CI job asserts that with its own
`git diff --exit-code` step. `--locked` was rejected as the alternative, since
it would fail a crate for lockfile drift and report that as a compile failure —
a different defect wearing this one's error message.

Failing on all three today would put the build red for three separate
migrations nobody has been asked to do, which teaches people to wave the gate
through. The estate has paid for that outcome once already. So the three are
recorded with their measured first error, which turns "invisible" into "tracked
and cannot regress further" without pretending they are fixed.

### Six ways the first version could have reported green anyway

Codex and CodeAnt reviewed it and found these. Each is real, and each is fixed.

1. **A broken crate getting worse still passed.** The comparison read `status`
   only, so a crate already recorded `broken` could acquire new errors and
   neither branch fired — on the gate whose stated purpose is making Rust
   dependency upgrades verifiable. The measured first error is now compared
   against the recorded one (`[CHANGED]`).
2. **The weekly run could not see the drift it exists for.** Every crate has a
   committed `Cargo.lock`, so plain `cargo check` reuses the locked graph and
   never resolves the newer releases a caret range allows. `--unlocked` copies
   manifest and sources to a temporary directory without the lock and compiles
   there — which is also exactly what the three worker Dockerfiles do. The
   scheduled run uses it.
3. **A cargo failure that was not a compile failure read as `broken`.** A
   registry outage, a missing toolchain or a timeout produced the same verdict
   as a type error, so an estate-wide network problem would have been recorded
   as "these crates do not compile". Such a run now reports `[BLOCKED]` and
   fails: a gate that cannot see must not report what a healthy estate reports.
4. **An unknown, misspelled or null ledger status was accepted silently**, so a
   typo could disable regression checking while the gate said PASSED. The
   vocabulary is closed and `broken` must carry a reason.
5. **Restoring `Cargo.lock` hid lockfile drift** where `git diff --exit-code`
   could not see it. Now reported as `[LOCKFILE STALE]` — and still restored,
   because the gate must not change what it measures.
6. **A crate nested under another crate's directory was dropped from
   discovery.** Membership is established with `cargo metadata` rather than
   assumed from nesting.

Fixing (1) exposed a seventh, in the fix itself: `--message-format short`
prints a diagnostic as `src/main.rs:290:44: error[E0308]: …`, starting with the
*path*. Filtering on `startswith("error")` therefore matched only cargo's
"could not compile" summary — the same line for every failure, and so unable to
tell one from another. `[CHANGED]` would have been defeated on the day it was
added.

### What (5) found on `main`

`src/nanoservices/rust/tranc3-nanoservice`'s committed `Cargo.lock` did not
satisfy its manifest. Corroborated independently:

```
$ cargo check --locked
error: cannot update the lock file … because --locked was passed to prevent this
```

Any reproducible or release build using `--locked` failed on that crate, and
nothing reported it. The lock is refreshed here and `--locked` now exits 0.

### What is still not checked, said rather than implied

Each crate is compiled for the host, plus any target the ledger records for it.
`aeonmind/wasm` carries `wasm32-unknown-unknown`, because it is the WASM
artifact and nothing compiled it for that target. `aeonmind/rust` deliberately
does not: its default features pull `pyo3-ffi`, whose build script needs a
Python interpreter for the target, so a plain `--target` check fails for a
reason that is not the code — measured, not assumed. Its WASM path is
feature-gated and is covered by this workflow's existing `check` job
(`cargo build --features wasm`). A recorded target that is not installed makes
the crate `[BLOCKED]`, never quietly passed on the host alone.

### Mutation testing

Every branch of the comparison was made to fail before it was trusted:

| Perturbation | Result |
|---|---|
| Remove a crate from the ledger | `[UNRECORDED]`, rc=1 |
| Record a broken crate as `ok` | `[REGRESSED]`, rc=1 |
| Record a compiling crate as `broken` | `[FIXED, UNRECORDED]`, rc=1 |
| Add a crate to the ledger that is not in the tree | `[GONE]`, rc=1 |
| Plant a real type error in `workers/vault-service-rs` | `[REGRESSED]` naming `error[E0308]` at the planted line, rc=1 |
| Change a recorded `broken` crate's `reason` prose | nothing: prose is not compared |
| Change a recorded `broken` crate's `errors` set | `[changed, not gating]`, **rc=0** |
| Misspell a ledger status (`okay`) | `[LEDGER]`, rc=1 |
| Record `broken` with no reason | `[LEDGER]`, rc=1 |
| Record a target that is not installed | `[BLOCKED]`, rc=1 |
| Restore the stale `Cargo.lock` | `[LOCKFILE STALE]`, rc=1 |

Baseline restores to rc=0 in every case, with a clean working tree. Both modes
pass today and report the same first errors: `locked` and `unlocked` agree,
which is the state the weekly run exists to notice a departure from.

## What this gate does not catch

Stated rather than left implicit, because a control's blind spots are the part
people most need told.

**A crate that breaks differently.** This is the big one, and it is a blind
spot arrived at by measurement rather than chosen. The gate reports a
diagnostic difference on an already-broken crate as a **notice, and does not
fail on it.** Two attempts to make it a gating assertion were both disproved
by CI on `src/nanoservices/nsa_broker`, which reported a change with the same
primary `E0433` at the same line both times:

1. Comparing the full multiset of diagnostics. rustc's error *recovery*
   differs between releases, so the number of consequent errors one root cause
   produces is a property of the compiler.
2. Comparing the set of distinct error codes. The *kinds* move too — a newer
   rustc reclassifies and suppresses follow-on errors from the same defect.

The diagnostics a compiler emits for broken code are not a stable property of
that code unless the compiler is pinned, and `rust.yml` uses
`dtolnay/rust-toolchain@stable`. Gating on it means the **three**
recorded-broken crates go red on every rustc release for a reason unrelated
to the code — three, not nine, because the comparison only runs for entries
the ledger records as broken; the six that compile measure no diagnostics at
all. Three is still every broken crate in the tree, on every release, and
that is precisely the failure mode that gets `|| true` attached — the defect
this gate exists to stop repeating. **Pinning the toolchain is what would let
this be promoted back to an assertion.** Until then the honest claim is
narrower than the one this document originally made: the gate catches a crate
that *stops compiling*, not one that breaks *differently*.

What still gates, and is toolchain-stable: a crate recorded as compiling that
no longer does ([REGRESSED]), one that compiles and is recorded broken
([FIXED, UNRECORDED]), one in the tree and not in the ledger ([UNRECORDED]),
one in the ledger and not in the tree ([GONE]), one that could not be checked
at all ([BLOCKED]), a lockfile the manifest no longer satisfies
([LOCKFILE STALE]), and the ledger's own validity rules ([LEDGER]).

**Prose and location.** Neither is compared, for the same reason: rustc
rewords its messages between releases, and a comment inserted above a failing
line moves it. Both are still recorded and printed, because a human reading a
notice needs them to decide which side is right.

**Runtime behaviour.** This gate compiles; it does not run. A crate that
compiles can still be wrong.

## 6. What is not fixed here

The three broken crates are recorded, not repaired. Each needs its own change,
and they are independent:

- `workers/nexus-ws-rs` — nine mechanical `String` → `Utf8Bytes` conversions.
  This is the urgent one: it is a compose service whose image cannot be built.
- `src/nanoservices/nsa_broker` — a hyper 1.x migration plus two genuine borrow
  errors, which need a reading of what the code meant to do.
- `rust_extensions/tranc3_crypto` — a pyo3 0.29 migration and one aes-gcm 0.11
  import. Until it lands, `src/security/rust_crypto.py` is always on its Python
  fallback, and its info-level log should be raised to a warning so that fact
  is visible at ordinary log levels.

Landing any of them requires refreshing the ledger in the same change, which is
what the `[FIXED, UNRECORDED]` branch above exists to enforce.
