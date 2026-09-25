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
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import src.cmdb.containers as containers_module  # noqa: E402
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


# ── A sensor that cannot see must not report what a clean estate reports ─────


def test_an_unreadable_inventory_raises_rather_than_reporting_zero():
    """The defect IMMUNE-SYSTEM.md names, found in this repository's own CMDB.

    `discover()` returned an empty list when PyYAML was missing or the compose
    file was absent. `build_ci_register.py` then exited 0 and printed
    "containers with no SBOM: 0" -- a report of perfect coverage produced by a
    run that had enumerated nothing at all. An empty list now means "the compose
    file was read and declares no services", which is a measurement; anything
    that prevents a measurement raises.
    """
    from src.cmdb.containers import CannotEnumerateContainers

    assert issubclass(CannotEnumerateContainers, Exception)

    original = containers_module.COMPOSE
    try:
        containers_module.COMPOSE = REPO / "does-not-exist-compose.yml"
        with pytest.raises(CannotEnumerateContainers):
            containers_module.discover()
    finally:
        containers_module.COMPOSE = original


@pytest.mark.parametrize(
    "script", ["scripts/build_ci_register.py", "scripts/build_container_sboms.py"]
)
def test_the_generators_refuse_to_run_blind(script, tmp_path):
    """Both must exit non-zero when the inventory cannot be read.

    Exercised by making `import yaml` fail, which is how this was found: the
    scripts ran in an environment without PyYAML and reported a clean estate.
    """
    stub = tmp_path / "yamlblock"
    stub.mkdir()
    (stub / "yaml.py").write_text("raise ImportError('simulated: PyYAML missing')\n")

    result = subprocess.run(
        [sys.executable, script, "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(stub)},
    )
    assert result.returncode != 0, (
        f"{script} exited 0 with no readable container inventory. A generator that "
        "reports success on an estate it could not enumerate is worse than one "
        "that crashes."
    )
    combined = result.stdout + result.stderr
    assert "PyYAML" in combined, (
        f"{script} failed without naming the cause. The earlier message blamed the "
        "compose file for every failure, so a missing PyYAML read as a missing file."
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


class TestThePartialCheckout:
    """A register generated from a partial tree describes a smaller estate.

    `ci.yml`'s topology job checked out with `fetch-depth: 0` and no submodules,
    so `workers/cranbania` and `compliance/magna-carta` were empty directories.
    Every scan that walks the tree simply found nothing there, and
    `build_ci_register.py` regenerated one line shorter -- dropping
    `workers/cranbania/package.json` from the CranBania container CI's evidence.
    `--check` therefore reported STALE in that job and passed on every machine
    that had the submodules, which is indistinguishable from a developer having
    forgotten to regenerate.

    One line of difference, and the shape is what matters: the register is the
    estate's CMDB and `workers/cranbania` is The Town Hall.
    """

    def test_the_generator_refuses_a_checkout_missing_a_declared_submodule(self, tmp_path):
        """Refusing beats measuring a smaller estate and reporting it as the estate."""
        import src.cmdb.containers as containers

        (tmp_path / ".gitmodules").write_text(
            '[submodule "workers/cranbania"]\n'
            "\tpath = workers/cranbania\n"
            "\turl = https://github.com/Trancendos/CranBania\n",
            encoding="utf-8",
        )
        (tmp_path / "workers" / "cranbania").mkdir(parents=True)  # present, empty

        original = containers.REPO
        try:
            containers.REPO = tmp_path
            assert containers._absent_submodules() == ["workers/cranbania"]
        finally:
            containers.REPO = original

    def test_a_populated_submodule_is_not_reported_absent(self, tmp_path):
        """The other half: a checked-out submodule must not trip the guard."""
        import src.cmdb.containers as containers

        (tmp_path / ".gitmodules").write_text(
            '[submodule "workers/cranbania"]\n\tpath = workers/cranbania\n',
            encoding="utf-8",
        )
        sub = tmp_path / "workers" / "cranbania"
        sub.mkdir(parents=True)
        (sub / "package.json").write_text("{}", encoding="utf-8")

        original = containers.REPO
        try:
            containers.REPO = tmp_path
            assert containers._absent_submodules() == []
        finally:
            containers.REPO = original

    def test_this_repository_has_its_submodules(self):
        """The guard is worth nothing if it never has anything to check."""
        import src.cmdb.containers as containers

        assert (containers.REPO / ".gitmodules").is_file(), "no submodules declared"
        assert containers._absent_submodules() == []

    def test_every_job_running_a_generator_checks_out_submodules(self):
        """The workflow half of the contract, asserted rather than remembered.

        A generator that reads submodule content must not run in a job that
        does not check submodules out. Stating it here is what stops the next
        job being added without them.
        """
        import yaml

        workflow = yaml.safe_load((REPO / ".github/workflows/ci.yml").read_text())
        generators = ("build_ci_register.py", "build_container_sboms.py")

        offenders = []
        for name, job in workflow["jobs"].items():
            steps = job.get("steps", [])
            runs_generator = any(
                any(g in str(step.get("run", "")) for g in generators) for step in steps
            )
            if not runs_generator:
                continue
            checkout = next(
                (s for s in steps if "actions/checkout" in str(s.get("uses", ""))), None
            )
            with_ = (checkout or {}).get("with") or {}
            if with_.get("submodules") != "recursive":
                offenders.append(f"{name} (submodules={with_.get('submodules')!r})")

        assert not offenders, (
            "these ci.yml jobs run a register generator without checking out "
            "submodules, so they measure a smaller estate than the one the "
            "committed register describes: " + ", ".join(offenders)
        )


class TestTheDockerfileResolution:
    """Compose resolves `dockerfile:` against `context:`, not the repository root.

    Reading it as repo-relative turned the estate's commonest build shape --

        build:
          context: ./workers/nexus-ws-rs
          dockerfile: Dockerfile

    -- into `Path("Dockerfile").parent == "."`, so the scan read the ROOT
    Dockerfile and globbed the ROOT's requirements*.txt. Measured before the fix:
    74 of 88 built containers carried a bare `dockerfile:` filename, all 74 were
    attributed the root manifests, and **87 of 88 reported the same base image**.
    The container half of the CMDB was describing one image 87 times.

    The three Rust services are where it showed plainest: they build FROM
    rust:1.79-slim onto debian:bookworm-slim and ship a Cargo.lock and no
    requirements at all, yet each had a 76-package Python SBOM. Raised by cubic.
    """

    def test_a_bare_dockerfile_resolves_against_the_context(self):
        from src.cmdb.containers import _resolve_dockerfile

        assert (
            _resolve_dockerfile("./workers/nexus-ws-rs", "Dockerfile")
            == "workers/nexus-ws-rs/Dockerfile"
        )

    def test_an_already_qualified_dockerfile_is_left_alone(self):
        from src.cmdb.containers import _resolve_dockerfile

        assert (
            _resolve_dockerfile(".", "workers/the-lab/Dockerfile") == "workers/the-lab/Dockerfile"
        )

    def test_a_context_with_no_such_dockerfile_falls_back(self):
        """A join that does not exist must not invent a path."""
        from src.cmdb.containers import _resolve_dockerfile

        assert _resolve_dockerfile("./no/such/dir", "Dockerfile") == "Dockerfile"

    def test_the_estate_does_not_report_one_base_image_for_everything(self):
        """The property that would have caught this without anyone reading code.

        88 built containers sharing a single base image is not an estate, it is a
        scan resolving every path to the same file.
        """
        register = json.loads((REPO / "docs/architecture/ci-register.json").read_text())
        built = [
            ci
            for ci in register["configuration_items"]
            if str(ci.get("ci_id", "")).startswith("CI-CT-") and ci.get("provenance") == "built"
        ]
        distinct = {tuple(ci.get("base_images") or ()) for ci in built}

        assert len(built) > 20, "expected a substantial built-container population"
        assert len(distinct) > 1, (
            f"all {len(built)} built containers report the same base image "
            f"{next(iter(distinct))} — the Dockerfile path is not being resolved "
            "against the build context"
        )

    def test_a_rust_container_is_not_inventoried_as_python(self):
        """Ecosystem agreement: a Rust image must not carry pypi components."""
        register = json.loads((REPO / "docs/architecture/ci-register.json").read_text())
        rust = [
            ci
            for ci in register["configuration_items"]
            if any("rust:" in base for base in (ci.get("base_images") or []))
        ]
        assert rust, "expected the three Rust services in the register"

        for ci in rust:
            sbom = json.loads(
                (
                    REPO / "docs/architecture/sbom" / f"{ci['ci_id'][len('CI-CT-') :]}.cdx.json"
                ).read_text()
            )
            purls = [c.get("purl", "") for c in sbom["components"]]
            assert purls, f"{ci['ci_id']} has a Cargo.lock but an empty SBOM"
            assert all(p.startswith("pkg:cargo/") for p in purls), (
                f"{ci['ci_id']} is a Rust container but its SBOM lists non-cargo "
                f"components: {[p for p in purls if not p.startswith('pkg:cargo/')][:5]}"
            )


class TestTheRegisterDoesNotDependOnWalkOrder:
    """The register must describe the estate, not the filesystem it was built on.

    `build_ci_register.py --check` went STALE in CI four times while exiting 0 on
    every local checkout. The unified diff `--check` grew in the last commit
    finally named it, and it was not a forgotten regeneration -- it was two
    generator defects that make the output depend on `Path.rglob` order, which
    differs between filesystems:

      * `discover()` sorted on `(engine, name)`, which is not unique. Two modules
        called `pool.py` and two called `sentinel_station.py` each produce a store
        named `redis@pool` / `redis@sentinel_station`, so two pairs of CIs tied
        and Python's stable sort settled them by discovery order. Two
        Configuration Items swapping identity between two runs is a CMDB
        describing the machine rather than the estate.
      * a store reached by several path literals (`/data/hive.db` in one worker,
        `hive.db` in another) took its `locator` from whichever file the walk hit
        first, via `setdefault`. Eleven of the 144 datastore CIs are in that
        state.

    Both are the engagement's recurring shape once more: the control ran, exited,
    and reported -- and what it reported was decided by something other than what
    it was measuring.
    """

    def _reversed_walk(self, monkeypatch):
        from src.cmdb import datastores

        original = list(datastores._candidate_files())
        monkeypatch.setattr(datastores, "_candidate_files", lambda: reversed(original))

    def test_every_datastore_ci_id_is_unique(self):
        """The sort key must identify a CI, not merely group it."""
        from src.cmdb.datastores import discover

        ids = [store.ci_id for store in discover()]
        duplicated = sorted({i for i in ids if ids.count(i) > 1})
        assert not duplicated, f"datastore CI ids collide: {duplicated}"

    def test_the_register_is_byte_identical_under_a_reversed_walk(self, monkeypatch):
        """The property that would have caught this without a CI runner."""
        from src.cmdb.datastores import discover

        forward = [store.as_ci() for store in discover()]
        self._reversed_walk(monkeypatch)
        backward = [store.as_ci() for store in discover()]

        assert json.dumps(forward, indent=2) == json.dumps(backward, indent=2), (
            "the datastore register changes when the directory walk changes "
            "order — the generator is reporting the filesystem, not the estate"
        )

    def test_the_locator_is_the_most_specific_literal_whatever_the_order(self):
        """`/data/hive.db` says where the store lives; `hive.db` does not."""
        from src.cmdb.datastores import Datastore

        forward = Datastore(name="hive.db", engine="sqlite", locator="")
        for literal in ("data/hive.db", "hive.db"):
            forward.record_locator(literal)
        backward = Datastore(name="hive.db", engine="sqlite", locator="")
        for literal in ("hive.db", "data/hive.db"):
            backward.record_locator(literal)

        assert forward.locator == backward.locator == "data/hive.db"

    def test_a_store_two_locations_open_names_both(self):
        """`studio.db` is opened by Sashas Photo Studio and by The Studio.

        Jurisdiction was "first claimant wins", and the first claimant was
        whichever file the walk reached first -- so this store's owning Location
        changed between runs. For an estate planning per-Location databases, two
        Locations sharing one SQLite file is the finding; silently awarding it to
        one of them is the register answering a question it had not resolved.
        """
        from src.cmdb.datastores import discover

        shared = [store for store in discover() if len(store.locations) > 1]
        assert shared, "expected at least one store claimed by two Locations"
        for store in shared:
            assert store.location == sorted(store.locations)[0]
            assert "jurisdictions" in store.as_ci()

    def test_this_repository_actually_contains_a_merged_store(self):
        """Otherwise the two properties above pass by having nothing to check.

        A guard whose subject does not occur reports exactly what a clean estate
        reports. This one asserts its own subject exists: at least one datastore
        really is reached by more than one path literal, and the register
        discloses both rather than resolving the ambiguity away in silence.
        """
        from src.cmdb.datastores import discover

        merged = [store for store in discover() if len(store.locators) > 1]
        assert merged, "expected at least one store reached by two path literals"

        register = json.loads((REPO / "docs/architecture/ci-register.json").read_text())
        disclosed = [
            ci for ci in register["configuration_items"] if len(ci.get("locators") or []) > 1
        ]
        assert disclosed, "merged stores are not disclosing their alternate locators"
