# Estate Protection Matrices — Tranc3 Cross-Link

**Source of truth:** [Trancendos/magna-carta](https://github.com/Trancendos/magna-carta) repository, `docs/compliance/`

This platform's four estate-protection compliance matrices are authored and maintained in the
Magna Carta repository (this platform's compliance framework, `compliance/magna-carta/` submodule
— see `CLAUDE.md`'s Named subsystems table), not duplicated here. This file is a pointer, not a
copy, per the decision to keep Magna Carta as the single source of truth with a cross-linked
reference from Tranc3.

| Matrix | Register | Link |
|---|---|---|
| License Compliance Matrix | MC-012 | [LICENSE-COMPLIANCE-MATRIX.md](https://github.com/Trancendos/magna-carta/blob/main/docs/compliance/LICENSE-COMPLIANCE-MATRIX.md) |
| Intellectual Property Matrix | MC-013 | [INTELLECTUAL-PROPERTY-MATRIX.md](https://github.com/Trancendos/magna-carta/blob/main/docs/compliance/INTELLECTUAL-PROPERTY-MATRIX.md) |
| Encryption Matrix | MC-014 | [ENCRYPTION-MATRIX.md](https://github.com/Trancendos/magna-carta/blob/main/docs/compliance/ENCRYPTION-MATRIX.md) |
| Security Matrix | MC-015 | [SECURITY-MATRIX.md](https://github.com/Trancendos/magna-carta/blob/main/docs/compliance/SECURITY-MATRIX.md) |

Machine-readable register (all four, one file): [compliance/estate_protection_matrices.yaml](https://github.com/Trancendos/magna-carta/blob/main/compliance/estate_protection_matrices.yaml).

## Why these matrices live in Magna Carta, not Tranc3

Every other MC-### requirement, register, and compliance artefact for this platform already lives
in Magna Carta (`compliance/magna_carta_register.yaml`, `docs/compliance/REGULATION-MATRIX.md`,
`docs/compliance/TRANC3-REGISTER-BRIDGE.md`). These four matrices follow that same convention
rather than starting a second, competing compliance-documentation location inside Tranc3. The
Encryption and Security matrices in particular are grounded in a direct audit of *this* repo's
code (`docker-compose.production.yml`, `src/auth/`, `src/security/middleware.py`, `workers/*/`),
but the findings themselves are recorded in Magna Carta so they sit alongside the rest of the
platform's compliance register rather than fragmenting it.

## What these matrices found in this repo (summary — see the matrices themselves for detail)

- **Encryption (MC-014):** P0 services (auth, vault, AI backend) currently route on plain HTTP in
  `docker-compose.production.yml`, not TLS; Traefik's `letsencrypt` certresolver is referenced by
  ~21 service labels but never actually defined; 18 workers fall back to a hardcoded `"dev-secret"`
  `INTERNAL_SECRET` if the environment variable is unset.
- **Security (MC-015):** six in-repo routers (`src/imind/routes.py`, `src/vrar3d/routes.py`,
  `src/resonate/routes.py`, `src/artifactory/routes.py`, `src/library/routes.py`,
  `src/studio/routes.py`) have zero auth enforcement, including two unauthenticated delete
  endpoints; 65 files across `workers/*/` carry wildcard CORS.
- **License Compliance (MC-012):** a real `pip-licenses` scan of 190 installed packages; 4 packages
  remain unclassified pending manual license lookup.
- **Intellectual Property (MC-013):** no trademark clearance search has been performed for any of
  the 43 platform entity names — tracked as an open item, not asserted as cleared.

None of these findings have been remediated by the documentation pass that produced the matrices —
they are tracked as open action items in `compliance/estate_protection_matrices.yaml`'s
`action_items` per matrix, per Magna Carta's own honesty rule (do not claim compliance in product
copy unless the row is ✅ with evidence — `REGULATION-MATRIX.md` §5).

**Next review:** 2026-10-24 (aligned with the Magna Carta matrices' own quarterly cycle).
