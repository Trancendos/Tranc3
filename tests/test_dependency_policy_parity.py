"""The two dependency bots must agree about what is blocked.

`renovate.json` and `.github/dependabot.yml` both propose upgrades into the
same directories, and neither reads the other. A policy written in one is
therefore enforced on one path and open on the other -- which is not a
hypothetical: the React-ecosystem major block added to `renovate.json` in
#1242 left `npm /web` with no dependabot ignore at all, and #1203 ("Bump
react, react-dom and @types/react in /web") arrived through the gap.

This is the same shape as the rest of that PR's findings: a control that
covers one route and reports nothing about the other.

The first version of this file was that shape too. It unioned every ignore
in `.github/dependabot.yml` into one repository-wide set, so an ignore in
*any* block satisfied parity for *every* block: dropping `torch` from the
root `pip` entry while `/tranc3-bots` and `/workers` kept theirs left the
root `requirements.txt` open and the test green. It also compared only
presence, never update types, so an ignore covering less than renovate
disables read as full parity. Both are fixed below, and both limits are
asserted against rather than described.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
RENOVATE = REPO / "renovate.json"
DEPENDABOT = REPO / ".github/dependabot.yml"

#: renovate writes `matchPackageNames` as anchored regexes (`/^react$/`) for
#: exact names. Only those are compared -- a genuine pattern rule cannot be
#: restated as a dependabot `dependency-name`, so it is out of scope here
#: rather than silently treated as covered. This also excludes the bare-name
#: rule for the five centrally pinned packages (fastapi, starlette, pydantic,
#: uvicorn, redis), which `scripts/check_canonical_pin_governance.py` owns.
_EXACT = re.compile(r"^/\^([A-Za-z0-9@._/-]+)\$/$")

#: renovate's update-type vocabulary mapped onto dependabot's.
_UPDATE_TYPE = {
    "major": "version-update:semver-major",
    "minor": "version-update:semver-minor",
    "patch": "version-update:semver-patch",
}

_IMAGE = re.compile(r"^\s*image:\s*[\"']?([A-Za-z0-9][A-Za-z0-9._/-]*)", re.MULTILINE)
_FROM = re.compile(
    r"^\s*FROM\s+(?:--\S+\s+)*([A-Za-z0-9][A-Za-z0-9._/-]*)", re.MULTILINE | re.IGNORECASE
)


def _renovate_blocked() -> dict[str, set[str]]:
    """Exact package name -> the dependabot update types renovate disables."""
    document = json.loads(RENOVATE.read_text(encoding="utf-8"))
    blocked: dict[str, set[str]] = {}
    for rule in document.get("packageRules") or []:
        if rule.get("enabled") is not False:
            continue
        types = {_UPDATE_TYPE[t] for t in (rule.get("matchUpdateTypes") or []) if t in _UPDATE_TYPE}
        if not types:
            # No matchUpdateTypes means the rule disables everything, which
            # dependabot expresses as an ignore with no `update-types` at all.
            # Comparing those needs a different assertion than this file makes,
            # so they are left to check_canonical_pin_governance.py.
            continue
        for entry in rule.get("matchPackageNames") or []:
            # fullmatch, not match: `$` also matches before a trailing newline,
            # so `.match()` would accept `/^react$/\n` and parse it as `react`.
            # scripts/check_anchored_validators.py fails CI on exactly this,
            # and caught it here.
            found = _EXACT.fullmatch(str(entry))
            if found:
                blocked.setdefault(found.group(1), set()).update(types)
    return blocked


def _dependabot_blocks() -> list[dict]:
    """Every update block, with its ignores kept per block rather than unioned."""
    document = yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))
    blocks: list[dict] = []
    for update in document.get("updates") or []:
        ignores: dict[str, set[str] | None] = {}
        for entry in update.get("ignore") or []:
            name = str(entry.get("dependency-name", ""))
            types = entry.get("update-types")
            ignores[name] = set(types) if types else None
        blocks.append(
            {
                "ecosystem": str(update.get("package-ecosystem", "")),
                "directory": str(update.get("directory") or update.get("directories") or ""),
                "ignores": ignores,
            }
        )
    return blocks


def _declared_packages(ecosystem: str, directory: str) -> set[str] | None:
    """What the manifest directly in `directory` declares, or None if unmodelled.

    None means "this ecosystem's manifest layout is not modelled here", which
    is different from "this directory declares nothing" -- the caller skips it
    rather than reading an empty set as a clean result.
    """
    root = REPO / directory.lstrip("/")
    if not root.is_dir():
        return None

    if ecosystem == "npm":
        manifest = root / "package.json"
        if not manifest.is_file():
            return None
        document = json.loads(manifest.read_text(encoding="utf-8"))
        names: set[str] = set()
        for section in (
            "dependencies",
            "devDependencies",
            "peerDependencies",
            "optionalDependencies",
        ):
            names |= set((document.get(section) or {}).keys())
        return names

    if ecosystem == "pip":
        names = set()
        found = False
        # rglob, not glob: dependabot's pip ecosystem searches below the
        # directory it is given. Proven on 6bcb75c9 -- `pip in /workers`
        # succeeded against a directory whose only requirements files are one
        # level down, on the same commit where `docker in /workers` failed for
        # finding nothing.
        for manifest in sorted(root.rglob("requirements*.txt")):
            found = True
            for line in manifest.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith(("#", "-")):
                    continue
                names.add(re.split(r"[\[<>=!~;\s]", line, maxsplit=1)[0].lower())
        for pyproject in sorted(root.rglob("pyproject.toml")):
            found = True
            for match in re.finditer(
                r"^\s*[\"']([A-Za-z0-9._-]+)[\[<>=!~\"']",
                pyproject.read_text(encoding="utf-8"),
                re.MULTILINE,
            ):
                names.add(match.group(1).lower())
        return names if found else None

    return None


def _declared_images() -> set[str]:
    """Every container image the tree actually declares."""
    names: set[str] = set()
    for path in REPO.rglob("*"):
        if not path.is_file() or "node_modules" in path.parts or ".git" in path.parts:
            continue
        if path.suffix in {".yml", ".yaml"}:
            names |= set(_IMAGE.findall(path.read_text(errors="ignore")))
        elif path.name.startswith("Dockerfile"):
            names |= set(_FROM.findall(path.read_text(errors="ignore")))
    return names


def test_every_package_renovate_blocks_is_also_ignored_by_dependabot() -> None:
    """A block in one config and not the other is a block only half the time."""
    blocked = _renovate_blocked()
    assert blocked, "no exact-name blocks found in renovate.json -- has the shape changed?"

    covered = {name for block in _dependabot_blocks() for name in block["ignores"]}
    missing = sorted(set(blocked) - covered)
    assert not missing, (
        "renovate.json blocks upgrades for these packages but "
        ".github/dependabot.yml does not ignore them anywhere, so dependabot "
        f"will keep proposing what the policy forbids: {missing}"
    )


def test_each_ignore_covers_every_update_type_renovate_disables() -> None:
    """Parity is about update types, not just the package name.

    renovate disables `major` *and* `minor` for the ML libraries. An ignore
    naming only `semver-major` reads as parity while dependabot goes on
    proposing the minor upgrades the policy says need manual compatibility
    testing -- which is what the first version of this file permitted.
    """
    blocked = _renovate_blocked()
    thin: list[str] = []
    for block in _dependabot_blocks():
        for name, types in block["ignores"].items():
            if name not in blocked:
                continue
            if types is None:
                continue  # ignores everything: strictly stronger than renovate
            short = blocked[name] - types
            if short:
                thin.append(
                    f"{name} in {block['ecosystem']} {block['directory']}: missing {sorted(short)}"
                )

    assert not thin, (
        "these ignores cover less than renovate.json disables, so the blocked "
        f"update types still arrive through dependabot: {thin}"
    )


def test_a_block_ignores_every_blocked_package_its_own_manifest_declares() -> None:
    """One directory's ignore must not cover for another's.

    dependabot evaluates each update block independently: `pip /` does not
    read `pip /workers`. Dropping `torch` from the root `pip` entry while the
    other two keep theirs leaves the root `requirements.txt` open, and the
    union this file used to build reported that as full parity.

    The demand is made per block, from the manifest that block's own
    `directory` declares -- `package.json` for npm, `requirements*.txt` and
    `pyproject.toml` for pip.

    **How far down that search goes is per-ecosystem, and this file used to
    state it wrongly.** It said dependabot "reads that directory's manifest,
    directly, not recursively" for both. Measured on commit `6bcb75c9`, where
    a config change made dependabot re-evaluate all twelve blocks at once:
    `pip in /workers` **succeeded** and `docker in /workers` **failed** with
    `No Dockerfiles nor Kubernetes YAML found`, from the same directory, which
    holds no manifest of either kind directly and 84 requirements files and 90
    Dockerfiles one level down. pip recurses. docker does not.

    So pip is searched recursively here and npm is not. npm stays direct
    because recursing from the root would pull `web/package.json` into the
    root npm block and demand six React ignores for a manifest holding only
    undici, vite and ws -- and unlike pip, nothing has yet been measured that
    settles npm's real behaviour, so the narrower reading is the honest one.

    Limits, stated rather than implied. Only npm and pip are covered here,
    because those are the two ecosystems where "the manifest for directory D"
    is unambiguous; docker dependencies are scattered across Dockerfiles and
    compose files, covered instead by the tree-wide name check below and by
    `test_every_docker_block_has_a_dockerfile_in_its_own_directory`. An ignore
    repeated into a block whose manifest does not declare the package is left
    alone -- it is inert, not wrong, and already correct if that package is
    added there later.
    """
    blocked = _renovate_blocked()
    gaps: list[str] = []

    for block in _dependabot_blocks():
        declared = _declared_packages(block["ecosystem"], block["directory"])
        if declared is None:
            continue
        for name in sorted(set(blocked) & declared):
            if name not in block["ignores"]:
                gaps.append(
                    f"{name} is declared by {block['ecosystem']} "
                    f"{block['directory']} but that block does not ignore it"
                )

    assert not gaps, (
        "renovate.json blocks these packages, and dependabot reads them from a "
        f"manifest in a block that carries no matching ignore: {gaps}"
    )


def test_a_block_never_holds_a_security_patch() -> None:
    """Blocking an upgrade must not block its security fixes.

    This is the security question a dependency-policy change has to answer,
    and it is why `.github/dependabot.yml` counts as a security-sensitive
    surface: an ignore covering `semver-patch` would hold a CVE fix released
    as a patch, and an ignore with no `update-types` at all holds *every*
    update for that package.

    The invariant is derived, not asserted as a constant: renovate disables
    `major` for React and the databases and `major`+`minor` for the ML
    libraries, and never `patch` for any of them, so no parity ignore may
    block patch either. Patch is the path security fixes overwhelmingly
    travel.

    The pre-existing pip ignores (fastapi, starlette, pydantic, uvicorn,
    redis) deliberately hold all update types, because those five are pinned
    centrally by `scripts/align_framework_pins.py` and arrive as one reviewed
    pass rather than 63 identical line changes. They are governed by
    `scripts/check_canonical_pin_governance.py`, are not exact-name renovate
    blocks, and so fall outside `blocked` by construction rather than by an
    exception list here.

    The residual risk is stated rather than hidden: a fix that exists *only*
    in a new major is held until the migration renovate.json already calls
    "a decision, not an update" is made.
    """
    blocked = _renovate_blocked()
    assert all("version-update:semver-patch" not in types for types in blocked.values()), (
        "renovate.json now disables patch updates -- that is a security decision, not parity"
    )

    overbroad: list[str] = []
    for block in _dependabot_blocks():
        for name, types in block["ignores"].items():
            if name not in blocked:
                continue
            if types is None or "version-update:semver-patch" in types:
                overbroad.append(
                    f"{name} in {block['ecosystem']} {block['directory']}: "
                    f"{sorted(types) if types else 'ALL updates'}"
                )

    assert not overbroad, (
        "these parity ignores hold patch releases, so a security fix shipped "
        f"as a patch would never be proposed: {overbroad}"
    )


def test_every_docker_ignore_names_an_image_the_tree_declares() -> None:
    """An ignore for an image that does not exist blocks nothing.

    `renovate.json` carried `/^clickhouse$/` and this file copied it across
    six dependabot blocks. The tree declares `clickhouse/clickhouse-server`,
    which is the name both bots resolve the dependency to -- so the rule had
    never matched anything, in either config, while reading as an enforced
    migration-planning policy. A selector that cannot match is the same defect
    as a check that cannot fail.
    """
    declared = _declared_images()
    assert declared, "no container images found in the tree -- has the layout changed?"

    unmatched: list[str] = []
    for block in _dependabot_blocks():
        if block["ecosystem"] != "docker":
            continue
        for name in block["ignores"]:
            if name not in declared:
                unmatched.append(f"{name} (in {block['directory']})")

    assert not unmatched, (
        "these docker ignores name images the tree never declares, so they "
        f"block nothing: {sorted(set(unmatched))}"
    )


def _looks_like_kubernetes(path: Path) -> bool:
    """Whether a YAML file is a Kubernetes manifest dependabot's docker ecosystem reads.

    Judged on the two fields every manifest carries rather than on the
    filename, and tolerant of multi-document files. A parse failure reads as
    "not a manifest" rather than raising: this helper decides whether a
    directory has something to scan, and an unreadable file is not something
    dependabot could scan either.
    """
    try:
        documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except (yaml.YAMLError, OSError):
        return False
    return any(isinstance(d, dict) and "apiVersion" in d and "kind" in d for d in documents)


def test_every_docker_block_can_find_something_to_scan() -> None:
    """A dependabot block pointing at a directory with nothing to read is dead.

    `.github/dependabot.yml` carried docker blocks for `/workers` and
    `/deploy`. Neither had ever found anything. dependabot's docker ecosystem
    does not search below the directory it is given; `/workers` holds its 90
    Dockerfiles one level down in `workers/<name>/Dockerfile`, and `/deploy`
    has no Dockerfile anywhere. Every run ended in
    `dependency_file_not_found: No Dockerfiles nor Kubernetes YAML found`.

    Nobody saw it for the ordinary reason: dependabot re-evaluates every block
    when the config changes, and until #1250 edited this file, none had. A
    control that fails silently and is only observed by accident is the defect
    this repository keeps finding, and a dead block is worse than no block --
    it reads on the page as coverage that does not exist.

    Asserted for docker only, and deliberately so. pip is measurably
    different: on the same commit, `pip in /workers` succeeded where `docker
    in /workers` failed, from a directory with no direct manifest of either
    kind. Extending this rule to pip would flag a block that demonstrably
    works. What is asserted here is what was measured, not what is tidy.
    """
    missing: list[str] = []
    for block in _dependabot_blocks():
        if block["ecosystem"] != "docker":
            continue
        root = REPO / block["directory"].lstrip("/")
        if not root.is_dir():
            missing.append(f"{block['directory']} (no such directory)")
            continue
        # is_file(), because a *directory* called `Dockerfile.d` would
        # otherwise satisfy a glob that only ever meant to find a file.
        if any(p.is_file() for p in root.glob("Dockerfile*")):
            continue
        # Kubernetes manifests count too. dependabot's own failure names both
        # -- "No Dockerfiles nor Kubernetes YAML found" -- so a block resting
        # on k8s YAML is legitimate, and flagging it would make this guard
        # reject a configuration that works.
        if any(_looks_like_kubernetes(p) for p in root.glob("*.y*ml")):
            continue
        deeper = len([p for p in root.rglob("Dockerfile*") if p.is_file()])
        missing.append(
            f"{block['directory']} (no Dockerfile or Kubernetes manifest directly here"
            + (f"; {deeper} Dockerfile(s) one or more levels down)" if deeper else ")")
        )

    assert not missing, (
        "these dependabot docker blocks point at directories holding no "
        "Dockerfile, so every run fails with dependency_file_not_found and the "
        f"block scans nothing: {missing}"
    )
