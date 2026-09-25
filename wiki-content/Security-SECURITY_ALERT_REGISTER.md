# Wiki: Security Alert Register

> **This page is a pointer. The register itself is
> [`SECURITY_ALERT_REGISTER.md`](https://github.com/Trancendos/Tranc3/blob/main/SECURITY_ALERT_REGISTER.md)
> at the repository root.**

## Why this page no longer holds the register

Until 2026-09-04 this page held a second, divergent copy. Two entries —
SEC-008 (`esbuild`, `ws`) and SEC-009 — existed *only* here, so the canonical
register carried no record of them at all, and the copy at the root carried
entries this one did not. Neither was complete and nothing said so.

PR #1201 made the root file canonical and recovered the two missing entries
into it. This page should have become a pointer in the same change and did
not, which left `tests/test_doc_duplication.py` red on `main` — two files
claiming the title "Security Alert Register", and a pointer test asserting a
pointer that was never written.

## Why a pointer rather than a deletion

The register is read during incidents, and a dead wiki link during an incident
is worse than a stale page. A pointer answers the question the reader actually
has — *where is the register?* — and cannot drift, because it holds no findings
to drift.

## What belongs here instead

Wiki pages are the **administrative** view: orientation, navigation, and
narrative. A disposition, its evidence, and the premises a guard enforces
belong beside the code that the guard reads
(`scripts/check_disposition_premises.py`), not in a copy that is updated when
somebody remembers.
