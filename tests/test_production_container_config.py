from pathlib import Path

WORKER_SERVICES = {
    "gbrain-bridge",
    "topology-service",
    "ledger-service",
    "model-router-service",
    "workflow-engine-service",
    "skills-benchmark-service",
    "langchain-integration-service",
    "deepagents-orchestrator-service",
    "vault-service",
}


def test_worker_dockerfiles_do_not_depend_on_curl_for_healthchecks():
    dockerfiles = sorted(Path("workers").glob("*/Dockerfile"))
    assert dockerfiles

    offenders = [
        str(path) for path in dockerfiles if "CMD curl -f http://localhost:" in path.read_text()
    ]
    assert offenders == []


def test_production_compose_worker_healthchecks_do_not_depend_on_curl():
    # Scoped to services built from our own workers/*/Dockerfile — those run
    # on python:3.11-slim without curl installed (see the sibling Dockerfile-
    # level test). Vendor images (qdrant, minio, mattermost, ...) and
    # tranc3-backend's root Dockerfile (which does install curl) are exempt:
    # curl is legitimately available there.
    import yaml

    compose = yaml.safe_load(Path("docker-compose.production.yml").read_text())
    offenders = []
    for name, svc in compose["services"].items():
        build = svc.get("build")
        if not isinstance(build, dict):
            continue
        dockerfile = build.get("dockerfile", "")
        if not str(dockerfile).startswith("workers/"):
            continue
        test = (svc.get("healthcheck") or {}).get("test")
        if test and "curl" in str(test):
            offenders.append(name)
    assert offenders == []


def test_p3_worker_services_have_buildable_docker_contexts():
    missing = []
    for service in sorted(WORKER_SERVICES):
        service_dir = Path("workers") / service
        if not (service_dir / "Dockerfile").exists():
            missing.append(f"{service}/Dockerfile")
        if not (service_dir / "requirements-worker.txt").exists():
            missing.append(f"{service}/requirements-worker.txt")

    assert missing == []
