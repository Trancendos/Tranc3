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
        str(path)
        for path in dockerfiles
        if "CMD curl -f http://localhost:" in path.read_text()
    ]
    assert offenders == []


def test_production_compose_worker_healthchecks_do_not_depend_on_curl():
    compose = Path("docker-compose.production.yml").read_text()
    assert '"CMD", "curl", "-f", "http://localhost:' not in compose


def test_p3_worker_services_have_buildable_docker_contexts():
    missing = []
    for service in sorted(WORKER_SERVICES):
        service_dir = Path("workers") / service
        if not (service_dir / "Dockerfile").exists():
            missing.append(f"{service}/Dockerfile")
        if not (service_dir / "requirements-worker.txt").exists():
            missing.append(f"{service}/requirements-worker.txt")

    assert missing == []
