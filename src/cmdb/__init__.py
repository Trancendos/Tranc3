"""Trancendos CMDB — a real relational domain model over the EA workbook.

The 19 CSV files under docs/architecture/ea-workbook/ remain the source of
truth (verify-before-document, hand-edited). This package turns that flat
CSV layer into an actual entity/attribute/relationship domain model — a
SQLite database with real foreign keys between Service, Application,
Deployment, CostReview, and AccessControlReview — so it can be queried
relationally instead of grep'd, and so live signal (health checks, alerts)
has somewhere structured to land next to the service it's about.

Regenerate with `python scripts/build_cmdb.py` after the CSVs change, same
convention as scripts/build_master_service_matrix.py. The resulting
data/cmdb.db is not committed (see .gitignore's `*.db`) — it's a build
artifact of the CSVs, not a second source of truth.
"""
