from pathlib import Path

from scripts.compose_contract_audit import audit, parse_port

ROOT = Path(__file__).parents[1]


def test_production_compose_obeys_enforced_contracts():
    report = audit(ROOT / "docker-compose.production.yml")

    assert report["errors"] == []
    assert report["services"] >= 80


def test_detects_overlapping_public_port_bindings(tmp_path):
    compose = tmp_path / "compose.yml"
    compose.write_text(
        "services:\n  first:\n    ports: ['8080:80']\n  second:\n    ports: ['8080:81']\n",
        encoding="utf-8",
    )

    report = audit(compose)

    assert any("host port 8080/tcp" in finding for finding in report["errors"])


def test_detects_public_control_plane_and_weak_secret_fallback(tmp_path):
    compose = tmp_path / "compose.yml"
    compose.write_text(
        "services:\n  vault:\n    ports: ['8200:8200']\n    environment:\n      JWT_SECRET: '${JWT_SECRET:-}'\n",
        encoding="utf-8",
    )

    report = audit(compose)

    assert any("control-plane service vault" in finding for finding in report["errors"])
    assert any("permits an empty JWT_SECRET" in finding for finding in report["errors"])


def test_parses_loopback_and_public_short_port_syntax():
    local = parse_port("grafana", "127.0.0.1:3001:3000")
    public = parse_port("traefik", "443:443")

    assert local is not None and local.is_public is False
    assert public is not None and public.is_public is True
