# Security Alert Register

> **This page is a pointer. The register itself is
> [`SECURITY_ALERT_REGISTER.md`](https://github.com/Trancendos/Tranc3/blob/main/SECURITY_ALERT_REGISTER.md)
> in the repository root.**

Canonical triage for Forgejo/CodeQL/Trivy findings. Status values:

| Status | Meaning |
|--------|---------|
| **FIX** | Code or manifest change required |
| **FP** | False positive — documented with rule/suppression |
| **SUPPRESS** | Known issue with `.trivyignore` / CodeQL note |
| **ACCEPT** | Accepted risk with owner + review date |

Full Forgejo export — run `python scripts/export_forgejo_code_scan_alerts.py --merge` with `FORGEJO_TOKEN` set; confirm **0 open Critical** in Forgejo UI.
