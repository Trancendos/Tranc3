# Security Alert Register (wiki pointer)

This page is a pointer. The security alert register lives at
[`SECURITY_ALERT_REGISTER.md`](../SECURITY_ALERT_REGISTER.md) in the repository
root, and that is the only copy.

## Why this page is not the register

Until 2026-09-26 this page was a second document with the same title, last
substantively updated 2026-09-11, holding a 134-line subset while the root
register held 1,500-plus lines. `scripts/check_doc_duplication.py` fails on a
shared H1 for exactly the reason that pair demonstrated: two documents claiming
to be the same thing drift, and each stays blind to the other's contents. Four
of the five Forgejo-export rows recorded here were absent from the root
register, and the root register's SEC-009…SEC-019 findings were absent from
here.

Everything this page held that the root register did not has been moved into
it, under *Appendix — scanner scope and procedures, merged from the wiki copy*:
the Forgejo export rows and procedure, the Kubernetes manifest hardening table,
the npm audit scope, the SAST scope, the KSV118 Trivy row, guard calibration,
the vulnerability census, and the verification commands. Nothing was dropped.

## Where to add a new entry

In [`SECURITY_ALERT_REGISTER.md`](../SECURITY_ALERT_REGISTER.md), under
**Open entries**, with a disposition (`FIX` / `FP` / `ACCEPT` / `SUPPRESS`),
the reasoning, and a review date. `scripts/security_score.py` reads that file
and nothing reads this one.
