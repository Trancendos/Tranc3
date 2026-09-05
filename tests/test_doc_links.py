"""Documentation links, and the two conventions the estate writes them in.

The wiki-content migration moved 62 documents at once and left eight links
pointing at files that had not existed for weeks — four of them in
`README.md`, the first document anybody reads. Nothing noticed, because a
link is not read until somebody clicks it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def checker():
    path = REPO / "scripts" / "check_doc_links.py"
    spec = importlib.util.spec_from_file_location("check_doc_links", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestBothConventionsResolve:
    def test_a_repository_style_link_resolves(self, checker):
        assert checker.resolve(REPO / "README.md", "docs/SECURITY-ASSESSMENT.md")

    def test_a_wiki_style_extensionless_link_resolves(self, checker):
        """Calibrated: dropping the extension-elided candidate fails this.

        The published wiki flattens `wiki-content/` into one namespace, so
        `[x](Architecture-THING)` is correct there. A checker requiring the
        `.md` reported 137 failures, 128 of them fine — and a gate that is
        wrong 128 times out of 137 is one nobody keeps.

        Restoring the elided extension is the whole mechanism. A separate
        `wiki-content/` search path was written too, measured against every
        link in the estate, found to resolve nothing these two did not, and
        removed: every wiki-style link already lives in that directory.
        """
        home = REPO / "wiki-content" / "Home.md"
        assert checker.resolve(home, "Architecture-CF_WORKER_MIGRATION_ROADMAP")

    def test_a_link_to_nothing_fails(self, checker):
        """Calibrated: returning True unconditionally fails this."""
        assert not checker.resolve(REPO / "README.md", "docs/NO-SUCH-DOCUMENT.md")

    def test_an_anchor_only_link_resolves(self, checker):
        assert checker.resolve(REPO / "README.md", "#architecture")

    def test_a_submodule_link_is_not_reported(self, checker):
        """Their files are real; they are checked in their own repository.

        Reporting them would make this gate depend on whether submodules
        happen to be checked out, which is a property of the runner.
        """
        assert checker.resolve(
            REPO / "docs" / "governance" / "AI-BOM.md",
            "../../compliance/magna-carta/docs/compliance/EU-CRA-PROFILE.md",
        )

    def test_an_external_link_is_never_fetched(self, checker):
        """A gate whose verdict depends on a third party fails for reasons
        unrelated to the tree."""
        source = (REPO / "scripts" / "check_doc_links.py").read_text(encoding="utf-8")
        assert "requests" not in source and "urllib.request" not in source


class TestTheEstate:
    def test_every_internal_link_resolves(self, checker):
        assert checker.broken() == []

    def test_the_readme_links_are_among_those_checked(self, checker):
        """The four that were broken were all here, so this is not incidental."""
        documents = {d.relative_to(REPO).as_posix() for d in checker.documents()}
        assert "README.md" in documents
        assert len(documents) > 300
