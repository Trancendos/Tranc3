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


@pytest.fixture(scope="module")
def checker():
    path = REPO / "scripts" / "check_doc_duplication.py"
    spec = importlib.util.spec_from_file_location("check_doc_duplication", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestWhatCountsAsADuplicate:
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
        """
        pointer = (
            "# Security Alert Register\n\n"
            "> This page is a pointer. The register itself is elsewhere.\n"
        )
        assert checker._is_pointer(pointer)

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
    def test_no_title_is_claimed_twice(self, checker):
        assert checker.duplicates() == {}

    def test_the_two_wiki_copies_are_now_pointers(self):
        for path in (
            "wiki-content/Security-SECURITY_ALERT_REGISTER.md",
            "wiki-content/Strategy-DOC-03-API-Reference.md",
        ):
            text = (REPO / path).read_text(encoding="utf-8")
            assert "This page is a pointer" in text, path
            assert len(text.splitlines()) < 60, path


class TestTheRecoveredAdvisories:
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
        """
        offenders = []
        for path in sorted((REPO / "cloudflare").glob("*/package.json")):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if "wrangler" not in manifest.get("devDependencies", {}):
                continue
            overrides = manifest.get("overrides", {})
            if "esbuild" not in overrides or "ws" not in overrides:
                offenders.append(str(path.relative_to(REPO)))
        assert offenders == []
