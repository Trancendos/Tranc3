"""Load docs/architecture/ea-workbook/*.csv into the CMDB SQLite database.

Idempotent: truncates and reloads every table each run, so the CSVs stay the
single source of truth — this is a build artifact, not a second place to
hand-edit data. Same convention as scripts/build_master_service_matrix.py.
"""

from __future__ import annotations

import csv
import os

from sqlalchemy.orm import Session

from src.cmdb.models import (
    AccessControlReview,
    Application,
    Base,
    CostReview,
    Deployment,
    Service,
    build_engine,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EA_DIR = os.path.join(REPO_ROOT, "docs", "architecture", "ea-workbook")


def _bool(value: str) -> bool | None:
    v = (value or "").strip().upper()
    if v == "TRUE":
        return True
    if v == "FALSE":
        return False
    return None


def _int(value: str) -> int | None:
    v = (value or "").strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _rows(filename: str):
    with open(os.path.join(EA_DIR, filename), newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def load_services(session: Session) -> int:
    n = 0
    for row in _rows("02_service_inventory.csv"):
        session.add(
            Service(
                service_id=row["ServiceID"],
                service_name=row["ServiceName"],
                description=row["Description"],
                service_type=row["ServiceType"],
                owner=row["Owner"],
                tier3_ai=row["Tier3AI"],
                tier2_prime=row["Tier2Prime"],
                status_code=row["StatusCode"],
                environment_id=row["EnvironmentID"],
                hosting_model=row["HostingModel"],
                deployment_id=row["DeploymentID"],
                health_check_interval=_int(row["HealthCheckInterval"]),
                health_check_timeout=_int(row["HealthCheckTimeout"]),
                health_check_path=row["HealthCheckPath"],
                criticality_code=row["CriticalityCode"],
                sla=row["SLA"],
                rpo_minutes=_int(row["RPOMinutes"]),
                rto_minutes=_int(row["RTOMinutes"]),
                max_response_time_ms=_int(row["MaxResponseTimeMs"]),
                depends_on_services=row["DependsOnServices"],
                depends_on_infrastructure=row["DependsOnInfrastructure"],
                data_classification=row["DataClassification"],
                compliance_frameworks=row["ComplianceFrameworks"],
                monitoring_enabled=_bool(row["MonitoringEnabled"]),
                alerting_enabled=_bool(row["AlertingEnabled"]),
                auto_scaling_enabled=_bool(row["AutoScalingEnabled"]),
                min_instances=_int(row["MinInstances"]),
                max_instances=_int(row["MaxInstances"]),
                notes=row["Notes"],
            )
        )
        n += 1
    return n


def load_applications(session: Session) -> tuple[int, int]:
    known_services = {sid for (sid,) in session.query(Service.service_id).all()}
    n = 0
    skipped = 0
    for row in _rows("03_application_catalogue.csv"):
        deps = row.get("DependsOnServices", "")
        service_id = next((sid for sid in known_services if sid in deps), None)
        session.add(
            Application(
                application_id=row["ApplicationID"],
                application_name=row["ApplicationName"],
                description=row["Description"],
                application_type=row["ApplicationType"],
                owner=row["Owner"],
                tier3_ai=row["Tier3AI"],
                status_code=row["StatusCode"],
                environment_id=row["EnvironmentID"],
                hosting_model=row["HostingModel"],
                runtime_version=row["RuntimeVersion"],
                framework_version=row["FrameworkVersion"],
                deployment_id=row["DeploymentID"],
                repository_url=row["RepositoryURL"],
                docker_image=row["DockerImage"],
                docker_registry=row["DockerRegistry"],
                criticality_code=row["CriticalityCode"],
                sla=row["SLA"],
                max_response_time_ms=_int(row["MaxResponseTimeMs"]),
                data_classification=row["DataClassification"],
                compliance_frameworks=row["ComplianceFrameworks"],
                depends_on_services=deps,
                depends_on_applications=row["DependsOnApplications"],
                external_dependencies=row["ExternalDependencies"],
                monitoring_enabled=_bool(row["MonitoringEnabled"]),
                alerting_enabled=_bool(row["AlertingEnabled"]),
                auto_scaling_enabled=_bool(row["AutoScalingEnabled"]),
                min_instances=_int(row["MinInstances"]),
                max_instances=_int(row["MaxInstances"]),
                health_check_path=row["HealthCheckPath"],
                health_check_interval=_int(row["HealthCheckInterval"]),
                notes=row["Notes"],
                service_id=service_id,
            )
        )
        n += 1
        if service_id is None:
            skipped += 1
    return n, skipped


def load_deployments(session: Session) -> int:
    known_services = {sid for (sid,) in session.query(Service.service_id).all()}
    known_apps = {aid for (aid,) in session.query(Application.application_id).all()}
    n = 0
    for row in _rows("06_service_deployments.csv"):
        sid = row["ServiceID"] if row["ServiceID"] in known_services else None
        aid = row["ApplicationID"] if row["ApplicationID"] in known_apps else None
        session.add(
            Deployment(
                deployment_id=row["DeploymentID"],
                environment_id=row["EnvironmentID"],
                owner=row["Owner"],
                status_code=row["StatusCode"],
                status_label=row["StatusLabel"],
                deployment_date=row["DeploymentDate"],
                deployment_duration=row["DeploymentDuration"],
                commit_hash=row["CommitHash"],
                commit_message=row["CommitMessage"],
                artifact_digest=row["ArtifactDigest"],
                artifact_version=row["ArtifactVersion"],
                pipeline_run_id=row["PipelineRunID"],
                pipeline_url=row["PipelineURL"],
                previous_deployment_id=row["PreviousDeploymentID"],
                rollback_deployment_id=row["RollbackDeploymentID"],
                health_check_status=row["HealthCheckStatus"],
                security_scan_status=row["SecurityScanStatus"],
                compliance_check_status=row["ComplianceCheckStatus"],
                canary_deployment=_bool(row["CanaryDeployment"]),
                canary_percentage=row["CanaryPercentage"],
                blue_green_deployment=_bool(row["BlueGreenDeployment"]),
                feature_flags=row["FeatureFlags"],
                data_migration_required=_bool(row["DataMigrationRequired"]),
                rollback_authorized=_bool(row["RollbackAuthorized"]),
                approved_by=row["ApprovedBy"],
                approval_date=row["ApprovalDate"],
                notes=row["Notes"],
                service_id=sid,
                application_id=aid,
            )
        )
        n += 1
    return n


def load_cost_reviews(session: Session) -> int:
    known_services = {sid for (sid,) in session.query(Service.service_id).all()}
    n = 0
    for row in _rows("18_cost_and_revenue_review.csv"):
        sid = row["ServiceID"] if row["ServiceID"] in known_services else None
        session.add(
            CostReview(
                review_id=row["ReviewID"],
                review_date=row["ReviewDate"],
                reviewed_by=row["ReviewedBy"],
                zero_cost_status=row["ZeroCostStatus"],
                zero_cost_notes=row["ZeroCostNotes"],
                monetization_candidate_idea=row["MonetizationCandidateIdea"],
                monetization_reviewed_by=row["MonetizationReviewedBy"],
                approval_stage=row["ApprovalStage"],
                notes=row["Notes"],
                service_id=sid,
            )
        )
        n += 1
    return n


def load_access_control_reviews(session: Session) -> int:
    known_services = {sid for (sid,) in session.query(Service.service_id).all()}
    n = 0
    for row in _rows("19_access_control_review.csv"):
        sid = row["ServiceID"] if row["ServiceID"] in known_services else None
        session.add(
            AccessControlReview(
                review_id=row["ReviewID"],
                review_date=row["ReviewDate"],
                reviewed_by=row["ReviewedBy"],
                auth_mechanism=row["AuthMechanism"],
                auth_mechanism_notes=row["AuthMechanismNotes"],
                data_classification=row["DataClassification"],
                differentiates_user_ai_agent_bot=_bool(row["DifferentiatesUserAIAgentBot"]),
                recommended_action=row["RecommendedAction"],
                notes=row["Notes"],
                service_id=sid,
            )
        )
        n += 1
    return n


def load_all(db_path: str) -> dict:
    engine = build_engine(db_path)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    Session = __import__("sqlalchemy.orm", fromlist=["sessionmaker"]).sessionmaker(bind=engine)
    session = Session()
    try:
        n_services = load_services(session)
        session.flush()
        n_apps, apps_unlinked = load_applications(session)
        session.flush()
        n_deployments = load_deployments(session)
        n_cost = load_cost_reviews(session)
        n_access = load_access_control_reviews(session)
        session.commit()
    finally:
        session.close()
    return {
        "services": n_services,
        "applications": n_apps,
        "applications_unlinked_to_service": apps_unlinked,
        "deployments": n_deployments,
        "cost_reviews": n_cost,
        "access_control_reviews": n_access,
    }
