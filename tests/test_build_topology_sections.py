"""Regression tests for measured service topology: volumes are not services."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_topology_3d as topology


class ComposeServiceBoundaryTests(unittest.TestCase):
    def test_named_volumes_and_networks_are_not_services(self):
        yaml = """version: "3.8"
x-common: &common
  restart: always
services:
  ice-box-service:
    image: python:3.11
    ports:
      - "8046:8046"
    labels:
      - "traefik.http.routers.ice.rule=PathPrefix(`/ice`)"
volumes:
  ice-box-quarantine:
    driver: local
networks:
  tranc3-net:
    driver: bridge
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "compose.yml"
            path.write_text(yaml, encoding="utf-8")
            with patch.object(topology, "COMPOSE", path):
                result = topology.compose_services()
        self.assertEqual(list(result), ["ice-box-service"])
        self.assertEqual(result["ice-box-service"]["port"], 8046)
        self.assertEqual(result["ice-box-service"]["prefix"], "/ice")

    def test_generated_service_count_matches_actual_services(self):
        path = Path(__file__).resolve().parents[1] / "docs/architecture/topology-3d.json"
        with path.open(encoding="utf-8") as handle:
            stored = json.load(handle)
        actual = topology.compose_services()
        self.assertEqual(stored["counts"]["compose_services"], len(actual))
        self.assertNotIn("ice-box-quarantine", actual)
        self.assertNotIn("tranc3-net", actual)


if __name__ == "__main__":
    unittest.main()
