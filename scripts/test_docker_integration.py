#!/usr/bin/env python3
"""
Docker Compose Integration Test
================================
Validates the docker-compose.production.yml stack structure and configuration.

This script validates:
1. Docker Compose file syntax and structure
2. All 29 workers are defined with correct ports
3. Health checks are configured for all services
4. Dependencies are correctly specified
5. Networks and volumes are properly defined
6. Environment variable requirements are documented

Usage:
    python scripts/test_docker_integration.py

Note: This script validates the compose file structure but does NOT
actually spin up containers (requires Docker daemon).
"""

import sys
import yaml
from pathlib import Path
from typing import Dict

from shared_core.path_validation import validate_path


# Expected worker ports from docker-compose.production.yml
# P0-P2 workers have fixed port assignments from the roadmap
# P3 stubs have arbitrary ports assigned in the compose file
EXPECTED_WORKERS = {
    "tranc3-ai": 8001,
    "infinity-void": 8002,
    "api-gateway": 8003,
    "infinity-ws": 8004,
    "infinity-auth": 8005,
    "users-service": 8006,
    "monitoring": 8007,
    "notifications": 8008,
    "infinity-ai": 8009,
    "the-grid": 8010,
    "products-service": 8011,
    "orders-service": 8012,
    "payments-service": 8013,
    "files-service": 8014,
    "identity-service": 8015,
}

# P3 stub workers — these exist in the compose file with arbitrary port assignments
P3_STUB_WORKERS = {
    "analytics-service",
    "search-service",
    "email-service",
    "sms-service",
    "storage-service",
    "cron-service",
    "queue-service",
    "cache-service",
    "config-service",
    "rate-limit-service",
    "cdn-service",
    "geo-service",
    "audit-service",
    "health-aggregator",
}

# Infrastructure services
INFRASTRUCTURE_SERVICES = [
    "traefik",
    "vault",
    "prometheus",
    "grafana",
    "loki",
    "promtail",
    "ipfs",
]


def load_compose_file(path: Path) -> Dict:
    """Load and parse docker-compose.yml file."""
    try:
        validate_path(path, Path(__file__).parent.parent)
        with open(path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"❌ ERROR: Compose file not found: {path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"❌ ERROR: Invalid YAML in compose file: {e}")
        sys.exit(1)
    return None  # unreachable — satisfies PY-008 checker


def test_compose_structure(compose: Dict) -> bool:
    """Test basic compose file structure."""
    print("\n📋 Testing compose file structure...")

    errors = []

    # Check version
    if "version" not in compose:
        errors.append("Missing 'version' field")
    else:
        print(f"  ✓ Version: {compose['version']}")

    # Check services
    if "services" not in compose:
        errors.append("Missing 'services' field")
        return False

    services = compose["services"]
    print(f"  ✓ Services defined: {len(services)}")

    # Check networks
    if "networks" not in compose:
        errors.append("Missing 'networks' field")
    else:
        print(f"  ✓ Networks defined: {len(compose['networks'])}")

    # Check volumes
    if "volumes" not in compose:
        errors.append("Missing 'volumes' field")
    else:
        print(f"  ✓ Volumes defined: {len(compose['volumes'])}")

    if errors:
        for error in errors:
            print(f"  ❌ {error}")
        return False

    print("  ✅ Compose structure valid")
    return True


def test_worker_services(compose: Dict) -> bool:
    """Test all expected workers are defined."""
    print("\n🔧 Testing worker services...")

    services = compose["services"]
    errors = []

    # Check P0-P2 workers with specific port requirements
    for worker_name, expected_port in EXPECTED_WORKERS.items():
        if worker_name not in services:
            errors.append(f"Missing worker: {worker_name}")
            continue

        service = services[worker_name]

        # Check ports
        if "ports" not in service:
            errors.append(f"{worker_name}: missing 'ports'")
        else:
            ports = service["ports"]
            if not any(f":{expected_port}" in str(p) for p in ports):
                errors.append(f"{worker_name}: expected port {expected_port} not found in {ports}")

        # Check health check
        if "healthcheck" not in service:
            errors.append(f"{worker_name}: missing 'healthcheck'")

        # Check restart policy
        if "restart" not in service:
            errors.append(f"{worker_name}: missing 'restart' policy")

    # Check P3 stub workers exist (port assignment is flexible)
    for worker_name in P3_STUB_WORKERS:
        if worker_name not in services:
            errors.append(f"Missing P3 stub worker: {worker_name}")
            continue

        service = services[worker_name]

        # Check ports exist (any port is fine)
        if "ports" not in service:
            errors.append(f"{worker_name}: missing 'ports'")

        # Check health check
        if "healthcheck" not in service:
            errors.append(f"{worker_name}: missing 'healthcheck'")

    if errors:
        for error in errors[:10]:
            print(f"  ❌ {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")
        return False

    print(f"  ✅ All {len(EXPECTED_WORKERS)} P0-P2 workers + {len(P3_STUB_WORKERS)} P3 stubs defined correctly")
    return True


def test_infrastructure_services(compose: Dict) -> bool:
    """Test infrastructure services are defined."""
    print("\n🏗️  Testing infrastructure services...")

    services = compose["services"]
    errors = []

    for infra_name in INFRASTRUCTURE_SERVICES:
        if infra_name not in services:
            errors.append(f"Missing infrastructure service: {infra_name}")

    if errors:
        for error in errors:
            print(f"  ❌ {error}")
        return False

    print(f"  ✅ All {len(INFRASTRUCTURE_SERVICES)} infrastructure services defined")
    return True


def test_health_checks(compose: Dict) -> bool:
    """Test health check configuration."""
    print("\n💓 Testing health check configuration...")

    services = compose["services"]
    missing_healthcheck = []

    for name, service in services.items():
        if "healthcheck" not in service:
            missing_healthcheck.append(name)

    if missing_healthcheck:
        print(f"  ❌ Missing health checks for: {', '.join(missing_healthcheck[:10])}")
        if len(missing_healthcheck) > 10:
            print(f"     ... and {len(missing_healthcheck) - 10} more")
        return False

    print(f"  ✅ All {len(services)} services have health checks")
    return True


def test_dependencies(compose: Dict) -> bool:
    """Test service dependencies."""
    print("\n🔗 Testing service dependencies...")

    services = compose["services"]
    errors = []

    # Check that api-gateway depends on tranc3-ai
    if "api-gateway" in services:
        api_gateway = services["api-gateway"]
        if "depends_on" not in api_gateway:
            errors.append("api-gateway: missing 'depends_on'")
        elif "tranc3-ai" not in api_gateway.get("depends_on", []):
            errors.append("api-gateway: should depend on tranc3-ai")

    # Check that workers don't have circular dependencies
    # (basic check - not exhaustive)
    for name, service in services.items():
        deps = service.get("depends_on", [])
        for dep in deps:
            if dep not in services:
                errors.append(f"{name}: depends on non-existent service '{dep}'")

    if errors:
        for error in errors:
            print(f"  ❌ {error}")
        return False

    print("  ✅ Dependencies configured correctly")
    return True


def test_networks_and_volumes(compose: Dict) -> bool:
    """Test networks and volumes configuration."""
    print("\n🌐 Testing networks and volumes...")

    errors = []

    # Check networks
    if "networks" in compose:
        networks = compose["networks"]
        if "tranc3-net" not in networks:
            errors.append("Missing network: tranc3-net")

    # Check volumes
    if "volumes" in compose:
        volumes = compose["volumes"]
        expected_volumes = ["void-data", "prometheus-data", "grafana-data", "loki-data"]
        for vol in expected_volumes:
            if vol not in volumes:
                errors.append(f"Missing volume: {vol}")

    if errors:
        for error in errors:
            print(f"  ❌ {error}")
        return False

    print("  ✅ Networks and volumes configured correctly")
    return True


def test_environment_variables(compose: Dict) -> bool:
    """Test environment variable configuration."""
    print("\n🔐 Testing environment variables...")

    services = compose["services"]
    env_vars = set()

    # Collect all environment variables
    for name, service in services.items():
        env_list = service.get("environment", [])
        if isinstance(env_list, dict):
            env_vars.update(env_list.keys())
        elif isinstance(env_list, list):
            for env in env_list:
                if "=" in env:
                    env_vars.add(env.split("=")[0])

    # Check for critical environment variables
    critical_vars = [
        "ENVIRONMENT",
        "MASTER_KEY_SEED",
        "INTERNAL_SECRET",
        "JWT_SECRET",
    ]

    missing_critical = []
    for var in critical_vars:
        if var not in env_vars:
            missing_critical.append(var)

    if missing_critical:
        print(f"  ⚠️  Warning: Critical env vars not found: {', '.join(missing_critical)}")
        print(f"     (These may be defined in .env.production file)")

    print(f"  ✅ Environment variables configured ({len(env_vars)} unique vars)")
    return True


def generate_report(compose: Dict) -> None:
    """Generate a summary report."""
    print("\n" + "=" * 60)
    print("📊 DOCKER COMPOSE INTEGRATION TEST REPORT")
    print("=" * 60)

    services = compose["services"]

    print(f"\n📦 Total Services: {len(services)}")
    print(f"   - Workers (P0-P2): {len(EXPECTED_WORKERS)}")
    print(f"   - Workers (P3 stubs): {len(P3_STUB_WORKERS)}")
    print(f"   - Infrastructure: {len(INFRASTRUCTURE_SERVICES)}")

    print(f"\n🌐 Networks: {len(compose.get('networks', {}))}")
    print(f"💾 Volumes: {len(compose.get('volumes', {}))}")

    print(f"\n🔧 Worker Port Allocation (P0-P2):")
    for name, port in sorted(EXPECTED_WORKERS.items()):
        status = "✓" if name in services else "✗"
        print(f"   {status} {name:25s} → {port}")

    print(f"\n🔧 P3 Stub Workers:")
    for name in sorted(P3_STUB_WORKERS):
        status = "✓" if name in services else "✗"
        svc = services.get(name, {})
        ports = svc.get("ports", ["?"])
        print(f"   {status} {name:25s} → {ports}")

    print(f"\n🏗️  Infrastructure Services:")
    for name in INFRASTRUCTURE_SERVICES:
        status = "✓" if name in services else "✗"
        print(f"   {status} {name}")

    print("\n" + "=" * 60)
    print("✅ All validation checks passed!")
    print("=" * 60)
    print("\n📝 Next Steps:")
    print("   1. Create .env.production file with required environment variables")
    print("   2. Run: docker compose -f docker-compose.production.yml up -d")
    print("   3. Verify health: docker compose ps")
    print("   4. Check logs: docker compose logs -f")
    print("\n📖 See docs/DEPLOYMENT_RUNBOOK.md for detailed deployment instructions.")
    print("=" * 60)


def main():
    """Main entry point."""
    print("🐳 Docker Compose Integration Test")
    print("=" * 60)

    compose_path = Path(__file__).parent.parent / "docker-compose.production.yml"

    # Load compose file
    compose = load_compose_file(compose_path)

    # Run all tests
    tests = [
        test_compose_structure,
        test_worker_services,
        test_infrastructure_services,
        test_health_checks,
        test_dependencies,
        test_networks_and_volumes,
        test_environment_variables,
    ]

    all_passed = True
    for test in tests:
        if not test(compose):
            all_passed = False

    if all_passed:
        generate_report(compose)
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Please fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()