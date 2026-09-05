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
    """The link checker, loaded from `scripts/` by path.

    Imported rather than shelled out to, so a test can call `resolve()` on one
    link instead of asserting against the whole estate's output.
    """
    path = REPO / "scripts" / "check_doc_links.py"
    spec = importlib.util.spec_from_file_location("check_doc_links", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestBothConventionsResolve:
    """The estate writes links two ways, and both have to resolve.

    Repository-style (`docs/X.md`) and wiki-style (`X`, extension elided).
    A checker that knows one of them fails documents written in the other.
    """

    def test_a_repository_style_link_resolves(self, checker):
        """The common case: a relative path with its extension."""
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
        """`#section` addresses this document; there is no file to find."""
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

    def test_an_external_link_is_never_fetched(self, checker, monkeypatch):
        """A gate whose verdict depends on a third party fails for reasons
        unrelated to the tree.

        This used to grep the checker's source for `requests` and
        `urllib.request`, which asserts nothing: `import urllib.request as u`,
        `http.client`, `subprocess.run(["curl", ...])` and a bare socket all
        pass that test while making the call. What has to hold is behavioural,
        so the socket itself is taken away and the whole estate — every
        external link in 300-odd documents, not one constructed example — is
        scanned with no network underneath it.
        """
        import socket

        def refuse(*args, **kwargs):
            """Stand-in for `socket.socket` that fails loudly if anything opens one."""
            raise AssertionError("check_doc_links.py opened a socket")

        monkeypatch.setattr(socket, "socket", refuse)
        monkeypatch.setattr(socket, "create_connection", refuse)

        assert checker.broken() == []

    def test_an_external_target_resolves_without_touching_the_filesystem(self, checker):
        """`resolve()` must not be reached for an external target at all.

        A URL that happened to contain a path fragment matching a real file
        would otherwise resolve for the wrong reason, and one that did not
        would be reported as a broken internal link.
        """
        assert "https://example.invalid/not/a/file.md".startswith(checker._EXTERNAL)
        assert not "docs/AI-BOM.md".startswith(checker._EXTERNAL)


class TestTheEstate:
    """The gate's verdict on the real tree, not on constructed examples."""

    def test_every_internal_link_resolves(self, checker):
        """The assertion the gate exists for, run against the whole estate."""
        assert checker.broken() == []

    def test_the_readme_links_are_among_those_checked(self, checker):
        """The four that were broken were all here, so this is not incidental."""
        documents = {d.relative_to(REPO).as_posix() for d in checker.documents()}
        assert "README.md" in documents
        assert len(documents) > 300
