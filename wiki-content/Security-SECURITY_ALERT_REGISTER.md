# Security Alert Register

> **This page is a pointer. The register itself is
> [`SECURITY_ALERT_REGISTER.md`](https://github.com/Trancendos/Tranc3/blob/main/SECURITY_ALERT_REGISTER.md)
> in the repository root.**

## Why this page no longer holds the register

Until 2026-09-04 this page held a second copy of the register, and the two had
diverged. The root copy is the live one — `scripts/security_score.py` reads it
(`_register_complete()`), where it contributes 12 points to the Security
dimension of the production readiness scorecard. This copy was read by people
and by nothing else.

The divergence cost something real. This page carried two advisories the root
register had never heard of — GHSA-67mh-4wv8-2f99 (`esbuild`) and
GHSA-3h5v-q93c-6h6q (`ws`), both transitive through `wrangler` — and asserted
that the `overrides` remedy was applied in *all* Cloudflare `package.json`
files. It was in one of seven. Six surfaces stood unremediated behind a
record that said otherwise, in a document the scanner never read.

Both advisories now live in the root register as **SEC-006**, with the
measured state rather than the claimed one, and all seven packages carry the
overrides. `scripts/check_doc_duplication.py` fails the build if a second
document starts claiming to be this register again.

## What belongs here instead

Wiki pages are the **administrative** view: orientation, navigation, and
narrative. When a document is read by a script, the script's copy is
canonical and the wiki links to it rather than restating it — restating is
how the two came apart.
