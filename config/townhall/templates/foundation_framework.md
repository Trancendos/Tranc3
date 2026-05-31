# The Foundation Framework

Charter for base platform services shared by all Trancendos locations.

## Pillars

1. Architectural — entity hierarchy (PID/AID/SID/NID)
2. Security — Cryptex, The Lighthouse, Infinity IAM
3. DevOps — The Citadel, The Workshop (Forgejo)
4. Knowledge — The Library, Observatory audit

## Mandatory controls

- `PLATFORM_INFRA_MODE` documented per environment
- Secrets in The Void / Vault — never in git
- Pre-deploy gate before production promote

## App extensions

Each location adds an **App per App Framework** appendix referencing this charter.
