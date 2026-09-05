"""The CMDB register and the entity register, which had parted on half the estate.

`src/entities/platform.py` is canonical (CLAUDE.md) and is what the solution-pack
generator, the flow contract and the surface-ownership check read.
`src/config/id_registry.json` is the CMDB's own record of the same 43 Locations,
and nothing compared them.

22 of 43 disagreed. Six Creativity Locations all claimed `src/studio/`, a router
recorded as unmounted and removed. Four named a different LIVE service: The Void
at `workers/config-service/`, Cryptex at `workers/rate-limit-service/`, Section 7
at `workers/geo-service/`, DevOcity at `workers/health-aggregator/`. A
configuration item pointing at another service's code answers every dependency
question about the wrong thing.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def checker():
    path = REPO / "scripts" / "check_id_registry_alignment.py"
    spec = importlib.util.spec_from_file_location("check_id_registry_alignment", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestTheRegistersAgree:
    def test_no_location_disagrees(self, checker):
        assert checker.drift() == []

    def test_every_location_is_actually_compared(self, checker):
        """A check over an empty intersection passes vacuously.

        Both registers key on PID, and a rename on one side would silently
        drop Locations out of the comparison rather than failing it.
        """
        registry = checker._registry_paths()
        entities = checker._entity_paths()
        assert len(set(registry) & set(entities)) >= 40

    def test_a_disagreement_is_reported(self, checker, monkeypatch):
        """Calibrated: returning [] regardless fails this."""
        monkeypatch.setattr(checker, "_registry_paths", lambda: {"PID-VOI": "workers/wrong/"})
        monkeypatch.setattr(checker, "_entity_paths", lambda: {"PID-VOI": "workers/infinity-void/"})
        failures = checker.drift()
        assert len(failures) == 1
        assert "workers/wrong/" in failures[0]

    def test_an_agreed_path_that_is_not_on_disk_is_reported(self, checker, monkeypatch):
        """Calibrated: comparing the two registers alone fails this.

        Both could agree on a directory that no longer exists — which is how
        `src/studio/` survived in six records for as long as it did.
        """
        monkeypatch.setattr(checker, "_registry_paths", lambda: {"PID-X": "workers/gone/"})
        monkeypatch.setattr(checker, "_entity_paths", lambda: {"PID-X": "workers/gone/"})
        failures = checker.drift()
        assert len(failures) == 1
        assert "not on disk" in failures[0]


class TestTheSpecificRecordsThatWereWrong:
    """The four that named a different live service, asserted by name."""

    @pytest.mark.parametrize(
        ("pid", "expected"),
        [
            ("PID-VOI", "workers/infinity-void/"),
            ("PID-CRX", "workers/cryptex/"),
            ("PID-DUT", "workers/the-dutchy/"),
            ("PID-DEV", "workers/devocity/"),
        ],
    )
    def test_the_record_names_its_own_service(self, checker, pid, expected):
        assert checker._registry_paths()[pid] == expected

    def test_no_record_still_points_at_the_removed_studio_router(self):
        registry = json.loads(
            (REPO / "src" / "config" / "id_registry.json").read_text(encoding="utf-8")
        )
        assert '"src/studio/"' not in json.dumps(registry)
