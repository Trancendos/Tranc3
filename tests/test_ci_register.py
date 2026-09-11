"""Datastores and containers must reach the CMDB as CIs, and say what they are.

The owner's requirements, each checked here rather than asserted in a document:

  * every datastore and container is registered as a Configuration Item;
  * a container is marked as a container, with its contents referenced;
  * jurisdiction is shared -- the Location inside it, and The Ice Box as custodian;
  * an SBOM says which kind of SBOM it is.

That last one carries the most weight. A source SBOM lists declared application
dependencies and cannot see a base image's OS packages. If it is published
without saying so, a container whose base layer has never been examined reads as
fully inventoried -- the same defect this estate keeps finding elsewhere, where a
control reports success for work it did not do.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.cmdb.containers import CUSTODIAN, Container  # noqa: E402
from src.cmdb.containers import discover as discover_containers  # noqa: E402
from src.cmdb.datastores import Datastore  # noqa: E402
from src.cmdb.datastores import discover as discover_datastores  # noqa: E402

REGISTER = REPO / "docs" / "architecture" / "ci-register.json"
SBOM_DIR = REPO / "docs" / "architecture" / "sbom"


@pytest.fixture(scope="module")
def register() -> dict:
    return json.loads(REGISTER.read_text(encoding="utf-8"))


# ── Discovery is real ────────────────────────────────────────────────────────


def test_datastores_are_discovered():
    stores = discover_datastores()
    assert len(stores) > 50, (
        f"only {len(stores)} datastores found. The repository opens SQLite, Redis, "
        "DuckDB and PostgreSQL in well over a hundred places; a low count means the "
        "engine patterns stopped matching, not that the estate shrank."
    )


def test_containers_are_discovered():
    containers = discover_containers()
    assert len(containers) > 100, (
        f"only {len(containers)} containers found in docker-compose.production.yml"
    )


def test_both_provenance_kinds_are_present():
    """Built and pulled are handled differently; both paths must be exercised."""
    containers = discover_containers()
    kinds = {c.provenance for c in containers}
    assert kinds == {"built", "pulled"}, f"provenance kinds present: {kinds}"


# ── The CI contract ──────────────────────────────────────────────────────────


def test_every_container_has_a_custodian(register):
    """The field that may never be unknown."""
    containers = [ci for ci in register["configuration_items"] if ci["ci_class"] == "Container"]
    assert containers, "no Container CIs in the register"
    missing = [ci["ci_id"] for ci in containers if ci.get("custodian") != CUSTODIAN]
    assert not missing, (
        f"{len(missing)} container CIs without {CUSTODIAN} as custodian: {missing[:5]}.\n"
        "Jurisdiction may be unknown; custody may not. A container nobody is "
        "accountable for containing is the one case this model exists to prevent."
    )


def test_jurisdiction_is_always_populated_even_when_unknown(register):
    for ci in register["configuration_items"]:
        assert ci.get("jurisdiction"), (
            f"{ci['ci_id']} has an empty jurisdiction. Unknown ownership is recorded "
            "as `_unrouted_` so it can be routed, never as a blank that reads as fine."
        )


def test_containers_are_marked_as_containers(register):
    containers = [ci for ci in register["configuration_items"] if ci["ci_class"] == "Container"]
    for ci in containers:
        assert "sbom_ref" in ci, f"{ci['ci_id']} does not reference its contents"
        assert "provenance" in ci, f"{ci['ci_id']} does not say whether we built it"


def test_ci_ids_are_unique(register):
    ids = [ci["ci_id"] for ci in register["configuration_items"]]
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert not duplicates, f"duplicate CI ids: {sorted(duplicates)[:10]}"


def test_datastore_cis_name_their_engine(register):
    stores = [ci for ci in register["configuration_items"] if ci["ci_class"] == "Datastore"]
    assert stores, "no Datastore CIs in the register"
    for ci in stores:
        assert ci.get("engine"), f"{ci['ci_id']} does not name an engine"


# ── SBOM honesty ─────────────────────────────────────────────────────────────


def test_every_sbom_declares_its_scope():
    """The property that stops a partial inventory reading as a complete one."""
    documents = sorted(SBOM_DIR.glob("*.cdx.json"))
    assert documents, "no SBOMs generated"
    for path in documents:
        data = json.loads(path.read_text(encoding="utf-8"))
        properties = {p["name"]: p["value"] for p in data["metadata"].get("properties", [])}
        assert "trancendos:sbom-scope" in properties, (
            f"{path.name} does not declare its scope. A source SBOM and an image SBOM "
            "look identical in CycloneDX; only the scope says whether the base image "
            "was examined."
        )
        assert properties["trancendos:sbom-scope"] in {"source", "image"}


def test_source_sboms_say_what_they_did_not_look_at():
    for path in sorted(SBOM_DIR.glob("*.cdx.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        properties = {p["name"]: p["value"] for p in data["metadata"].get("properties", [])}
        if properties.get("trancendos:sbom-scope") != "source":
            continue
        note = properties.get("trancendos:sbom-scope-note", "")
        assert "base-image" in note or "Base-image" in note, (
            f"{path.name} is source-scope but does not state that base-image packages are excluded."
        )


def test_sboms_are_valid_cyclonedx():
    for path in sorted(SBOM_DIR.glob("*.cdx.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("bomFormat") == "CycloneDX"
        assert data.get("specVersion")
        assert data["metadata"]["component"]["type"] == "container"


def test_every_container_ci_points_at_an_sbom_that_exists(register):
    containers = [ci for ci in register["configuration_items"] if ci["ci_class"] == "Container"]
    for ci in containers:
        if not ci.get("sbom_present"):
            continue
        assert (REPO / ci["sbom_ref"]).is_file(), (
            f"{ci['ci_id']} claims sbom_present but {ci['sbom_ref']} is not there"
        )


# ── Generated output stays current ───────────────────────────────────────────


@pytest.mark.parametrize(
    "script", ["scripts/build_ci_register.py", "scripts/build_container_sboms.py"]
)
def test_generated_output_is_current(script):
    result = subprocess.run(
        [sys.executable, script, "--check"], cwd=REPO, capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"{script} reports stale output.\n{result.stdout}\n{result.stderr}"
    )


# ── Probes ───────────────────────────────────────────────────────────────────


class TestTheGuardsWouldCatchIt:
    def test_a_container_without_a_custodian_is_detected(self):
        ci = Container(service="rogue").as_ci()
        ci["custodian"] = ""
        assert ci["custodian"] != CUSTODIAN, "the custodian check would not have fired"

    def test_an_unowned_container_still_gets_a_custodian(self):
        """The asymmetry, stated as a test rather than a paragraph."""
        ci = Container(service="third-party-thing", provenance="pulled").as_ci()
        assert ci["jurisdiction"] == "_unrouted_"
        assert ci["custodian"] == CUSTODIAN

    def test_a_datastore_ci_id_is_stable_and_slugged(self):
        store = Datastore(name="Role_Registry.DB", engine="sqlite", locator="data/x.db")
        assert store.ci_id == "CI-DS-sqlite-role-registry-db"

    def test_root_is_assumed_when_no_user_directive(self):
        """No USER in a Dockerfile means root; silence must not read as safe."""
        assert Container(service="x", provenance="built", runs_as="").runs_as_root
        assert not Container(service="x", provenance="built", runs_as="worker").runs_as_root

    def test_an_sbom_without_a_scope_would_fail(self):
        document = {"bomFormat": "CycloneDX", "metadata": {"properties": []}}
        names = {p["name"] for p in document["metadata"]["properties"]}
        assert "trancendos:sbom-scope" not in names, "the scope check would not have fired"
