"""CMDB domain model: the loader must turn every EA workbook CSV row into a
real row with working foreign keys, not silently drop or mis-link data."""

from __future__ import annotations

import tempfile

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")

from src.cmdb.loader import load_all  # noqa: E402
from src.cmdb.models import (  # noqa: E402
    AccessControlReview,
    CostReview,
    Deployment,
    Service,
    ServiceDocPack,
    build_engine,
)
from src.cmdb.service_docpack_map import DOCPACK_TO_SERVICE_ID  # noqa: E402


@pytest.fixture(scope="module")
def cmdb_session():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        stats = load_all(tmp.name)
        engine = build_engine(tmp.name)
        Session = sqlalchemy.orm.sessionmaker(bind=engine)
        session = Session()
        yield session, stats
        session.close()


def test_load_all_returns_nonzero_counts(cmdb_session):
    _, stats = cmdb_session
    assert stats["services"] > 0
    assert stats["applications"] > 0
    assert stats["deployments"] > 0
    assert stats["cost_reviews"] > 0
    assert stats["access_control_reviews"] > 0


def test_every_service_row_loaded(cmdb_session):
    session, stats = cmdb_session
    assert session.query(Service).count() == stats["services"]


def test_deployment_service_foreign_key_resolves(cmdb_session):
    """A Deployment's service_id, when set, must point at a real Service —
    proves the FK linking actually works, not just that both tables have rows."""
    session, _ = cmdb_session
    linked = session.query(Deployment).filter(Deployment.service_id.isnot(None)).all()
    assert linked, "expected at least one deployment linked to a service"
    known_ids = {s.service_id for s in session.query(Service.service_id).all()}
    for dep in linked:
        assert dep.service_id in known_ids


def test_access_control_review_join_finds_known_gap(cmdb_session):
    """Regression check for the real finding this table exists to surface:
    at least one Confidential/Restricted service with no auth mechanism."""
    session, _ = cmdb_session
    hits = (
        session.query(Service, AccessControlReview)
        .join(AccessControlReview, AccessControlReview.service_id == Service.service_id)
        .filter(Service.data_classification.in_(["DC-003", "DC-004"]))
        .filter(AccessControlReview.auth_mechanism.like("None detected%"))
        .all()
    )
    ids = {s.service_id for s, _ in hits}
    assert "SRV-SHARDS-001" in ids


def test_cost_review_service_link_mostly_resolves(cmdb_session):
    session, stats = cmdb_session
    linked = session.query(CostReview).filter(CostReview.service_id.isnot(None)).count()
    assert linked > 0
    assert linked <= stats["cost_reviews"]


def test_application_service_link_has_no_unlinked_rows(cmdb_session):
    """applications_unlinked_to_service tracks a real data-quality signal —
    every application should resolve to a service given a correct CSV."""
    _, stats = cmdb_session
    assert stats["applications_unlinked_to_service"] == 0


def test_service_doc_pack_count_matches_mapping(cmdb_session):
    """Every confidently-mapped doc-pack in service_docpack_map.py should
    load — this is running against the real docs/services/ tree, not a
    fixture, so a mismatch means a mapped slug's README.md went missing or a
    ServiceID stopped resolving, not a test-data problem."""
    session, stats = cmdb_session
    assert stats["service_doc_packs"] == len(DOCPACK_TO_SERVICE_ID)
    assert session.query(ServiceDocPack).count() == len(DOCPACK_TO_SERVICE_ID)


def test_service_doc_pack_foreign_key_resolves(cmdb_session):
    session, _ = cmdb_session
    known_ids = {s.service_id for s in session.query(Service.service_id).all()}
    for pack in session.query(ServiceDocPack).all():
        assert pack.service_id in known_ids


def test_the_spark_doc_pack_has_all_governance_sections(cmdb_session):
    """Regression check against a doc-pack known to be the reference
    implementation (docs/services/the-spark/README.md's own docstring
    calls it that) — it should have every governance section detected."""
    session, _ = cmdb_session
    pack = session.get(ServiceDocPack, "the-spark")
    assert pack is not None
    assert pack.service_id == "SRV-SPARK-001"
    assert pack.has_ddd
    assert pack.has_tasd
    assert pack.has_raci
    assert pack.has_gov
