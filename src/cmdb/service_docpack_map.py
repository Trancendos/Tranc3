"""Maps docs/services/<slug>/README.md doc-packs to CMDB ServiceIDs.

Hand-built, not fuzzy-matched. Fuzzy name-matching between health-aggregator
and the CMDB was tried and rejected earlier in this project (see
src/cmdb/health_sync.py's module docstring) after producing confirmed wrong
matches from unrelated cross-reference text — the same risk applies here, so
every entry below was checked individually against
docs/architecture/ea-workbook/02_service_inventory.csv (ServiceName, Owner,
Notes), not inferred from name similarity alone.

43 doc-packs exist under docs/services/ (see docs/services/INDEX.md). Only 34
have an unambiguous single matching CMDB Service row — either an exact
ServiceName match or an exact Owner match to a ServiceName that clearly
describes the same role. The other 9 are left OUT of DOCPACK_TO_SERVICE_ID
rather than guessed:

- Several Owner names (e.g. "Cornelius MacIntyre", "Trancendos") are shared
  across many unrelated CMDB rows and aren't a distinguishing signal.
- Several entities ("API Marketplace", "The Citadel", "Think Tank") have no
  CMDB Service row with a matching name at all — they may not be represented
  in the CMDB yet, or may be covered indirectly by an infrastructure/tooling
  row not named after the entity.
- A few (Arcadia, Arcadian Exchange, Royal Bank of Arcadia, DocUtari, The
  Lighthouse) have multiple plausible candidate rows (e.g. Royal Bank of
  Arcadia -> both SRV-PAYMENTS-001 and SRV-LEDGER-001) with no single clear
  "primary" — recording a guess here would misrepresent confidence.

UNMAPPED_DOCPACKS documents these with the reason, so this stays an honest,
auditable "not yet mapped" list rather than a silent gap.
"""

from __future__ import annotations

DOCPACK_TO_SERVICE_ID: dict[str, str] = {
    "chronosphere-arcstream": "SRV-CRON-001",
    "cryptex": "SRV-CRYPTEX-001",
    "devocity": "SRV-DEVOCITY-001",
    "fabulousa": "SRV-FABULOUSA-001",
    "i-mind": "SRV-IMIND-001",
    "imaginarium": "SRV-IMAGINARIUM-001",
    "infinity": "SRV-INF-001",
    "resonate": "SRV-RESONATE-001",
    "sashas-photo-studio": "SRV-SASHASPHOTO-001",
    "taimra": "SRV-TAIMRA-001",
    "tateking": "SRV-TATEKING-001",
    "the-academy": "SRV-ACADEMY-001",
    "the-artifactory": "SRV-ARTIFACTORY-001",
    "the-basement": "SRV-BASEMENT-001",
    "the-chaos-party": "SRV-CHAOSPARTY-001",
    "the-digital-grid": "SRV-THEGRID-001",
    "the-dutchy": "SRV-DUTCHY-001",
    "the-hive": "SRV-HIVE-001",
    "the-ice-box": "SRV-ICEBOX-001",
    "the-lab": "SRV-LAB-001",
    "the-library": "SRV-LIBRARY-001",
    "the-nexus": "SRV-WS-001",
    "the-observatory": "SRV-OBS-001",
    "the-spark": "SRV-SPARK-001",
    "the-studio": "SRV-STUDIOWORKER-001",
    "the-town-hall": "SRV-CRANBANIA-001",
    "the-void": "SRV-VOID-001",
    "the-warp-tunnel": "SRV-WARPTUNNEL-001",
    "the-workshop": "SRV-WORKSHOP-001",
    "tranceflow": "SRV-TRANCEFLOW-001",
    "tranquility": "SRV-TRANQUILITY-001",
    "turings-hub": "SRV-TURINGSHUB-001",
    "vrar3d": "SRV-VRAR3D-001",
    "warp-radio": "SRV-WARPRADIO-001",
}

UNMAPPED_DOCPACKS: dict[str, str] = {
    "api-marketplace": "No CMDB Service row with ServiceName or Owner matching "
    "'API Marketplace' / 'Solarscene' found in 02_service_inventory.csv.",
    "arcadia": "Owner 'Lilli SC' owns 2 rows (Notifications Service, Email "
    "Service) — neither named 'Arcadia'; no single unambiguous primary.",
    "arcadian-exchange": "Owner 'The Porter Family' owns 2 rows (Orders "
    "Service, Products Service) — neither named 'Arcadian Exchange'; no "
    "single unambiguous primary.",
    "docutari": "Owner 'To be Defined' owns 2 rows (Files Service, Storage "
    "Service) — ambiguous owner value, no unambiguous primary.",
    "luminous": "Owner 'Cornelius MacIntyre' is Tier2Prime on nearly every "
    "CMDB row (platform-wide oversight role), not a distinguishing signal; "
    "no row named 'Luminous'.",
    "royal-bank-of-arcadia": "Owner 'Dorris Fontaine' owns 2 plausible rows "
    "(Payments Service, Ledger Service) — no single unambiguous primary.",
    "the-citadel": "No CMDB Service row with ServiceName or Owner matching "
    "'The Citadel' / 'Trancendos' found.",
    "the-lighthouse": "Owner 'Rocking Ricki' owns 3 rows (Identity Service, "
    "The Warp Tunnel, Warp Radio) — none named 'The Lighthouse'; no single "
    "unambiguous primary.",
    "think-tank": "No CMDB Service row with ServiceName or Owner matching "
    "'Think Tank' / 'Trancendos' found.",
}
