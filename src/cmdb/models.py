"""CMDB domain model — Service / Application / Deployment / reviews, plus a
live HealthObservation table for trend detection to write into.

Column names and types mirror the EA workbook CSVs closely (see each class's
docstring for its source file) so the loader (loader.py) is a near-literal
copy, not a reinterpretation. Real ForeignKey relationships replace the
CSVs' plain-string ID cross-references (ServiceID, ApplicationID, ...).
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Service(Base):
    """docs/architecture/ea-workbook/02_service_inventory.csv"""

    __tablename__ = "services"

    service_id = Column(String(32), primary_key=True)
    service_name = Column(String(128))
    description = Column(Text)
    service_type = Column(String(32))
    owner = Column(String(64), index=True)
    tier3_ai = Column(String(64))
    tier2_prime = Column(String(64))
    status_code = Column(String(16), index=True)
    environment_id = Column(String(16))
    hosting_model = Column(String(16))
    deployment_id = Column(String(32))
    health_check_interval = Column(Integer)
    health_check_timeout = Column(Integer)
    health_check_path = Column(String(64))
    criticality_code = Column(String(16), index=True)
    sla = Column(String(16))
    rpo_minutes = Column(Integer)
    rto_minutes = Column(Integer)
    max_response_time_ms = Column(Integer)
    depends_on_services = Column(Text)  # semicolon-separated ServiceIDs — see Note below
    depends_on_infrastructure = Column(Text)
    data_classification = Column(String(16), index=True)
    compliance_frameworks = Column(Text)
    monitoring_enabled = Column(Boolean)
    alerting_enabled = Column(Boolean)
    auto_scaling_enabled = Column(Boolean)
    min_instances = Column(Integer)
    max_instances = Column(Integer)
    notes = Column(Text)

    applications = relationship("Application", back_populates="service")
    deployments = relationship("Deployment", back_populates="service")
    cost_reviews = relationship("CostReview", back_populates="service")
    access_control_reviews = relationship("AccessControlReview", back_populates="service")
    health_observations = relationship("HealthObservation", back_populates="service")

    # Note: DependsOnServices/DependsOnInfrastructure stay semicolon-separated
    # text columns rather than a many-to-many association table in this first
    # pass — the CSV values reference service names inconsistently (some IDs,
    # some free-text infra names like "SRV-CITADEL-01"), so a real FK-backed
    # dependency graph needs that data cleaned up first. Flagged, not solved.


class Application(Base):
    """docs/architecture/ea-workbook/03_application_catalogue.csv"""

    __tablename__ = "applications"

    application_id = Column(String(32), primary_key=True)
    application_name = Column(String(128))
    description = Column(Text)
    application_type = Column(String(32))
    owner = Column(String(64), index=True)
    tier3_ai = Column(String(64))
    status_code = Column(String(16), index=True)
    environment_id = Column(String(16))
    hosting_model = Column(String(16))
    runtime_version = Column(String(32))
    framework_version = Column(String(64))
    deployment_id = Column(String(32))
    repository_url = Column(String(256))
    docker_image = Column(String(128))
    docker_registry = Column(String(128))
    criticality_code = Column(String(16))
    sla = Column(String(16))
    max_response_time_ms = Column(Integer)
    data_classification = Column(String(16))
    compliance_frameworks = Column(Text)
    depends_on_services = Column(Text)
    depends_on_applications = Column(Text)
    external_dependencies = Column(Text)
    monitoring_enabled = Column(Boolean)
    alerting_enabled = Column(Boolean)
    auto_scaling_enabled = Column(Boolean)
    min_instances = Column(Integer)
    max_instances = Column(Integer)
    health_check_path = Column(String(64))
    health_check_interval = Column(Integer)
    notes = Column(Text)

    service_id = Column(String(32), ForeignKey("services.service_id"), index=True)
    service = relationship("Service", back_populates="applications")


class Deployment(Base):
    """docs/architecture/ea-workbook/06_service_deployments.csv"""

    __tablename__ = "deployments"

    deployment_id = Column(String(32), primary_key=True)
    environment_id = Column(String(16))
    owner = Column(String(64))
    status_code = Column(String(16), index=True)
    status_label = Column(String(64))
    deployment_date = Column(String(32))  # kept as text — source data is mixed ISO formats
    deployment_duration = Column(String(32))
    commit_hash = Column(String(64))
    commit_message = Column(Text)
    artifact_digest = Column(String(128))
    artifact_version = Column(String(32))
    pipeline_run_id = Column(String(64))
    pipeline_url = Column(String(256))
    previous_deployment_id = Column(String(32))
    rollback_deployment_id = Column(String(32))
    health_check_status = Column(String(32))
    security_scan_status = Column(String(32))
    compliance_check_status = Column(String(32))
    canary_deployment = Column(Boolean)
    canary_percentage = Column(String(16))
    blue_green_deployment = Column(Boolean)
    feature_flags = Column(Text)
    data_migration_required = Column(Boolean)
    rollback_authorized = Column(Boolean)
    approved_by = Column(String(64))
    approval_date = Column(String(32))
    notes = Column(Text)

    service_id = Column(String(32), ForeignKey("services.service_id"), index=True)
    application_id = Column(String(32), ForeignKey("applications.application_id"), index=True)
    service = relationship("Service", back_populates="deployments")
    application = relationship("Application")


class CostReview(Base):
    """docs/architecture/ea-workbook/18_cost_and_revenue_review.csv
    See docs/governance/COST-AND-REVENUE-GOVERNANCE.md for the policy this feeds."""

    __tablename__ = "cost_reviews"

    review_id = Column(String(32), primary_key=True)
    review_date = Column(String(16))
    reviewed_by = Column(String(64))
    zero_cost_status = Column(String(32), index=True)
    zero_cost_notes = Column(Text)
    monetization_candidate_idea = Column(Text)
    monetization_reviewed_by = Column(String(64))
    approval_stage = Column(Text)
    notes = Column(Text)

    service_id = Column(String(32), ForeignKey("services.service_id"), index=True)
    service = relationship("Service", back_populates="cost_reviews")


class AccessControlReview(Base):
    """docs/architecture/ea-workbook/19_access_control_review.csv
    See docs/governance/ACCESS-CONTROL-GOVERNANCE.md for the policy this feeds."""

    __tablename__ = "access_control_reviews"

    review_id = Column(String(32), primary_key=True)
    review_date = Column(String(16))
    reviewed_by = Column(String(64))
    auth_mechanism = Column(String(64), index=True)
    auth_mechanism_notes = Column(Text)
    data_classification = Column(String(16), index=True)
    differentiates_user_ai_agent_bot = Column(Boolean)
    recommended_action = Column(Text)
    notes = Column(Text)

    service_id = Column(String(32), ForeignKey("services.service_id"), index=True)
    service = relationship("Service", back_populates="access_control_reviews")


class HealthObservation(Base):
    """NOT sourced from a CSV — a live table for actual health-check results
    to land in over time, one row per observation. Empty until something
    (e.g. src/observability/proactive_health.py, or a new poller) writes to
    it — this table exists so there is somewhere structured for that data to
    go, which is the prerequisite for the trend-detection/predictive-analytics
    work requested but not yet built. See docs/governance/
    OBSERVABILITY-AND-AUTOMATION-GOVERNANCE.md for the wiring plan."""

    __tablename__ = "health_observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    service_id = Column(String(32), ForeignKey("services.service_id"), index=True)
    observed_at = Column(DateTime, index=True)
    health_score = Column(Float)  # 0.0-1.0, matching ProactiveHealthMonitor's convention
    status = Column(String(32))  # healthy | degraded | down — the 3 values
    # workers/health-aggregator/worker.py's _check_one() actually writes. Not enforced at
    # the DB layer: src/cmdb/health_sync.py stores this column's value verbatim from the
    # source row (preserving it for forensics) and only ever falls back to a health_score
    # of None (not a rewritten "unknown" status string) for a value outside that set.
    error_count = Column(Integer, default=0)
    response_time_ms = Column(Integer)
    source = Column(String(64))  # what recorded this — e.g. "health-aggregator", "manual"
    notes = Column(Text)

    service = relationship("Service", back_populates="health_observations")


class ServiceDocPack(Base):
    """NOT sourced from a CSV — one row per docs/services/<slug>/README.md
    that src/cmdb/service_docpack_map.py confidently maps to a real
    ServiceID. Records which of the doc-pack template's numbered governance
    sections (DDD, TASD, RACI, GOV — see docs/framework/
    SERVICE-DOC-PACK-TEMPLATE.md) are actually present in that file, so a SQL
    query can answer "which services have a RACI matrix on file" instead of
    grepping 43 files by hand. Only the doc-pack -> ServiceID link is
    represented here; the 9 doc-packs with no unambiguous ServiceID match
    (see service_docpack_map.UNMAPPED_DOCPACKS) have no row."""

    __tablename__ = "service_doc_packs"

    docpack_slug = Column(String(64), primary_key=True)  # e.g. "the-spark"
    doc_path = Column(String(128))  # e.g. "docs/services/the-spark/README.md"
    has_ddd = Column(Boolean, default=False)
    has_tasd = Column(Boolean, default=False)
    has_raci = Column(Boolean, default=False)
    has_gov = Column(Boolean, default=False)

    service_id = Column(String(32), ForeignKey("services.service_id"), index=True)
    service = relationship("Service")


def build_engine(db_path: str):
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return engine


def get_session_factory(engine):
    return sessionmaker(bind=engine)
