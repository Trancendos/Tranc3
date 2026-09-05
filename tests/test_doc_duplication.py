"""Two documents claiming to be the same thing, and what that cost.

`SECURITY_ALERT_REGISTER.md` (289 lines, read by `scripts/security_score.py`)
had a second copy at `wiki-content/Security-SECURITY_ALERT_REGISTER.md` (102
lines, read by people). The wiki copy carried two advisories the canonical
register had never heard of, and asserted their remedy was applied across all
seven Cloudflare packages. It was in one. Six surfaces stood unremediated
behind a record that said otherwise, in a document no scanner read — while the
register the scanner did read had no entry at all.

Neither copy was wrong about the other. Each was blind to it.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _version(text: str) -> tuple[int, ...]:
    """A dotted version as comparable integers, stopping at the first non-digit.

    Enough for the two npm packages below, whose advisory floors are plain
    `major.minor.patch`. A prerelease suffix is dropped rather than ordered,
    which reads a prerelease as its own release — the conservative direction
    here, since it can only make a borderline version look newer and so needs
    the floor to be genuinely cleared before it passes.
    """
    parts: list[int] = []
    for chunk in text.split("."):
        digits = ""
        for character in chunk:
            if not character.isdigit():
                break
            digits += character
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _lowest_admitted(spec: str) -> tuple[int, ...]:
    """The lowest version an npm override spec lets through.

    `0.28.2` admits only itself; `>=0.25.0` admits 0.25.0 upward. Both reduce
    to the same question — what is the floor — so both are read the same way.
    """
    return _version(spec.lstrip(">=^~ v"))


#: The version at which each advisory in SEC-008 is fixed. GHSA-67mh-4wv8-2f99
#: (esbuild dev-server request forgery) is fixed in 0.25.0; GHSA-3h5v-q93c-6h6q
#: (ws DoS via many HTTP headers) in 8.17.1, and the register's remedy set the
#: floor at 8.21.0, which is what is enforced.
_ADVISORY_FLOORS = {"esbuild": (0, 25, 0), "ws": (8, 21, 0)}


@pytest.fixture(scope="module")
def checker():
    """The duplication checker, loaded from `scripts/` by path."""
    path = REPO / "scripts" / "check_doc_duplication.py"
    spec = importlib.util.spec_from_file_location("check_doc_duplication", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestWhatCountsAsADuplicate:
    """Where the line falls between a second copy and a pointer to the first.

    Both halves matter: too strict and the remedy reads as the violation, too
    loose and a short second copy exempts itself.
    """

    def test_a_shared_title_is_a_duplicate(self, checker):
        """Calibrated: comparing content hashes fails this.

        The two copies had drifted, so no hash matched — which is precisely
        what made them dangerous. The shared title is the claim itself.
        """
        assert checker._normalise("# Security Alert Register".lstrip("# ")) == (
            checker._normalise("Security  ALERT  register!")
        )

    def test_a_pointer_page_is_not_a_duplicate(self, checker):
        """The resolution must not read as the violation.

        Replacing a copy with a page that names the canonical document is the
        fix; a check that failed on it would forbid its own remedy.

        The named path has to resolve. This test previously used "the register
        itself is elsewhere" and passed, which is what the tightening removed:
        a page saying a document exists somewhere leaves the reader exactly
        where a second copy would.
        """
        pointer = (
            "# Security Alert Register\n\n"
            "> This page is a pointer. The register itself is\n"
            "> [`SECURITY_ALERT_REGISTER.md`](SECURITY_ALERT_REGISTER.md) in the root.\n"
        )
        assert checker._is_pointer(pointer)

    def test_a_pointer_to_nowhere_is_still_a_duplicate(self, checker):
        """Calibrated against the version this replaced, which passed it.

        Both halves are needed and neither is sufficient: the phrase without a
        resolvable path points nowhere, and a resolvable path without the
        phrase is any document that happens to cite another one.
        """
        dangling = (
            "# Security Alert Register\n\n"
            "This page is a pointer. The register itself is `docs/not-a-real-file.md`.\n"
        )
        assert not checker._is_pointer(dangling)

        incidental = (
            "# Security Alert Register\n\n"
            "The canonical document is important; the wiki lives at a different URL.\n"
            "See SECURITY_ALERT_REGISTER.md.\n"
        )
        assert not checker._is_pointer(incidental)

    def test_a_pointer_may_name_its_target_as_a_github_url(self, checker):
        """Both live pointer pages link home by blob URL.

        They resolved only because their link TEXT happened to be the bare
        filename; a prose label would have broken them. The URL is the
        pointer, so the URL is read as one.
        """
        by_url = (
            "# Security Alert Register\n\n"
            "This page is a pointer. The register itself is [in the repository root]"
            "(https://github.com/Trancendos/Tranc3/blob/main/SECURITY_ALERT_REGISTER.md).\n"
        )
        assert checker._is_pointer(by_url)

    def test_a_long_page_is_not_a_pointer_however_it_is_worded(self, checker):
        """Calibrated: matching only the marker phrase fails this.

        Otherwise a full second copy escapes by adding one sentence.
        """
        text = "# X\n\nThis page is a pointer.\n" + "\n".join(f"line {i}" for i in range(200))
        assert not checker._is_pointer(text)

    def test_a_generic_title_is_not_a_duplicate(self, checker):
        """Every service has a README; that is structure, not duplication."""
        assert "readme" in checker._GENERIC


class TestTheEstate:
    """The gate's verdict on the real tree, not on constructed examples."""

    def test_no_title_is_claimed_twice(self, checker):
        """The assertion the gate exists for, run against the whole estate."""
        assert checker.duplicates() == {}

    def test_the_two_wiki_copies_are_now_pointers(self):
        """The resolution actually landed — both are pointers, not deletions."""
        for path in (
            "wiki-content/Security-SECURITY_ALERT_REGISTER.md",
            "wiki-content/Strategy-DOC-03-API-Reference.md",
        ):
            text = (REPO / path).read_text(encoding="utf-8")
            assert "This page is a pointer" in text, path
            assert len(text.splitlines()) < 60, path


class TestTheRecoveredAdvisories:
    """The two advisories the lost register copy carried, and their remedy.

    This suite is the reason the duplication gate exists: a record asserting a
    fix that six of seven packages never received.
    """

    def test_both_lost_advisories_are_in_the_canonical_register(self):
        """The point of consolidating: nothing the copy held may be dropped."""
        register = (REPO / "SECURITY_ALERT_REGISTER.md").read_text(encoding="utf-8")
        assert "GHSA-67mh-4wv8-2f99" in register
        assert "GHSA-3h5v-q93c-6h6q" in register

    def test_every_wrangler_package_carries_the_override_the_record_claims(self):
        """Calibrated: the record claimed all seven and one had it.

        A remediation asserted in a document and absent from six of seven
        packages is the defect this whole engagement is about, wearing a
        security record's clothes.

        Presence of the KEY is not the assertion. An earlier version of this
        test checked only that `esbuild` and `ws` appeared in `overrides`,
        which `{"esbuild": "0.24.0"}` — a version below the advisory floor —
        would have passed. What has to hold is that the version the override
        admits actually clears the advisory.
        """
        offenders = []
        for path in sorted((REPO / "cloudflare").glob("*/package.json")):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if "wrangler" not in manifest.get("devDependencies", {}):
                continue
            overrides = manifest.get("overrides", {})
            for package, floor in _ADVISORY_FLOORS.items():
                spec = overrides.get(package)
                if spec is None:
                    offenders.append(f"{path.relative_to(REPO)}: no {package} override")
                elif _lowest_admitted(spec) < floor:
                    offenders.append(f"{path.relative_to(REPO)}: {package} {spec} is below {floor}")
        assert offenders == []

    def test_the_lockfiles_resolve_a_remediated_version(self):
        """What `npm ci` installs is the lock, not the override.

        `deploy-cloudflare.yml` runs `npm ci && wrangler deploy`, and `npm ci`
        installs the resolved tree in `package-lock.json` — the override in
        `package.json` does not re-resolve anything at that point. So a lock
        generated before an override was added ships the version the override
        was written to displace, with the manifest still asserting otherwise.
        All three committed locks were in exactly that state: they carried
        esbuild 0.28.1 and ws 8.21.0/8.21.3 while the manifests said
        `>=0.25.0`/`>=8.21.0`, which those versions happened to satisfy — so
        nothing forced them and nothing would have noticed if they had not.
        """
        offenders = []
        for path in sorted((REPO / "cloudflare").glob("*/package-lock.json")):
            packages = json.loads(path.read_text(encoding="utf-8")).get("packages", {})
            for entry, meta in packages.items():
                name = entry.rsplit("node_modules/", 1)[-1]
                floor = _ADVISORY_FLOORS.get(name)
                if floor is None or "version" not in meta:
                    continue
                if _version(meta["version"]) < floor:
                    offenders.append(
                        f"{path.relative_to(REPO)}: {entry} at {meta['version']} is below {floor}"
                    )
        assert offenders == []
