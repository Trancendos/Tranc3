"""Calibration for the CI job dependency check.

Service Topology installed PyYAML and nothing else. Its guards grew to import
real platform modules — reading the language registry is the only way to check
the language registry — and the day `src/townhall/plm.py` imported the
event-type enum, the job died on `No module named 'pydantic'` several import
hops from anything the change touched.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.check_ci_job_dependencies import (  # noqa: E402
    _guarded,
    _import_time_nodes,
    _installed_modules,
    external_imports,
    main,
)


def _nodes(source: str):
    return _import_time_nodes(ast.parse(source).body)


class TestTheCheckPasses:
    def test_the_topology_job_installs_what_its_scripts_import(self):
        assert main(["--job", "topology"]) == 0

    def test_an_unknown_job_is_an_error_not_a_pass(self):
        """Calibrated: returning 0 for a missing job fails this.

        A check that silently passes when it cannot find its subject is the
        defect this whole engagement keeps finding.
        """
        assert main(["--job", "no-such-job"]) == 1


class TestWhatCountsAsAnImportTimeImport:
    def test_a_module_level_import_counts(self):
        assert len(_nodes("import pydantic\n")) == 1

    def test_an_import_inside_a_function_does_not(self):
        """Calibrated: walking the whole tree fails this.

        src/event_bus/bus.py imports httpx inside a webhook branch a
        documentation render never reaches. Failing on it would report a
        break that cannot happen, and a check that cries wolf gets muted.
        """
        assert _nodes("def f():\n    import httpx\n") == []

    def test_an_import_inside_a_class_body_counts(self):
        """A class body executes at import, unlike a function body."""
        assert len(_nodes("class C:\n    import pydantic\n")) == 1

    def test_an_import_guarded_against_importerror_does_not_count(self):
        """Calibrated: ignoring the try/except fails this.

        src/event_bus/nats_transport.py wraps nats in exactly this shape and
        calls it an optional import guard in a comment above it.
        """
        assert _nodes("try:\n    import nats\nexcept ImportError:\n    nats = None\n") == []

    def test_an_unguarded_try_still_counts(self):
        """Calibrated: skipping every try block fails this.

        `except ValueError` says nothing about the module being absent, so
        the import still has to succeed.
        """
        source = "try:\n    import pydantic\nexcept ValueError:\n    pass\n"
        assert len(_nodes(source)) == 1

    def test_a_bare_except_counts_as_guarded(self):
        assert _nodes("try:\n    import nats\nexcept:  # noqa: E722\n    pass\n") == []

    def test_an_import_under_a_module_level_if_counts(self):
        """Calibrated: only reading `tree.body` directly fails this.

        A conditional import at module level still runs on the branch taken.
        """
        nodes = _nodes("import os\nif os.name:\n    import pydantic\n")
        imported = {alias.name for node in nodes for alias in node.names}
        assert imported == {"os", "pydantic"}


class TestGuardDetection:
    def test_a_tuple_of_handlers_is_read(self):
        source = "try:\n    import nats\nexcept (ValueError, ImportError):\n    pass\n"
        assert _guarded(ast.parse(source).body[0].handlers)

    def test_an_unrelated_handler_is_not_a_guard(self):
        source = "try:\n    import nats\nexcept KeyError:\n    pass\n"
        assert not _guarded(ast.parse(source).body[0].handlers)


class TestLocalImportsAreFollowed:
    def test_a_repository_module_is_walked_rather_than_reported(self, tmp_path):
        """Calibrated: treating every import as external fails this.

        `src.creative.routing` is not a package to install; its own imports
        are what matter.
        """
        found = external_imports(REPO / "scripts" / "check_creative_routes.py")
        assert "src" not in found

    def test_a_transitive_dependency_is_reached(self):
        """The break itself: plm.py -> event_bus.types -> pydantic."""
        assert "pydantic" in external_imports(REPO / "scripts" / "generate_plm_docs.py")

    def test_a_relative_import_contributes_its_own_dependencies(self, tmp_path):
        """Calibrated: skipping relative imports entirely fails this.

        A relative import names a local module, so it adds no external name
        of its own — which is why it was skipped. But the module it names has
        imports too, and everything reachable only through one was invisible.
        """
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "helper.py").write_text("import pydantic\n", encoding="utf-8")
        entry = pkg / "entry.py"
        entry.write_text("from .helper import thing\n", encoding="utf-8")
        assert external_imports(entry) == {"pydantic"}

    def test_a_bare_relative_import_is_followed_too(self, tmp_path):
        """`from . import helper` names the sibling in its aliases."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "helper.py").write_text("import pydantic\n", encoding="utf-8")
        entry = pkg / "entry.py"
        entry.write_text("from . import helper\n", encoding="utf-8")
        assert external_imports(entry) == {"pydantic"}


class TestQuotedRequirements:
    """A version range has to be quoted for the shell, and quotes broke it."""

    def _provided(self, run: str):
        return _installed_modules({"steps": [{"run": run}]})

    def test_a_quoted_version_range_is_read(self):
        """Calibrated: splitting on whitespace fails this.

        `pip install "pydantic>=2,<3"` left the quote attached, so the module
        read as `"pydantic` and every script importing pydantic looked
        uninstalled — a check failing on a job that is in fact correct, which
        is how a check gets removed.
        """
        assert self._provided('pip install "pydantic>=2,<3"') == {"pydantic"}

    def test_a_single_quoted_pin_is_read(self):
        assert self._provided("pip install 'ruff==0.15.8'") == {"ruff"}

    def test_a_plain_name_still_works(self):
        assert self._provided("pip install PyYAML pydantic") == {"yaml", "pydantic"}

    def test_an_environment_marker_does_not_become_part_of_the_name(self):
        assert self._provided("pip install 'tomli; python_version<\"3.11\"'") == {"tomli"}


class TestUnguardedHandlerBodies:
    def test_an_import_in_an_unguarded_handler_counts(self):
        """Calibrated: reading only the try body fails this.

        `except OSError: import tomllib` runs at import time on the failing
        branch. Skipping handler bodies made a real dependency invisible —
        the same blind spot as skipping the try body would be.
        """
        source = "try:\n    import x\nexcept ValueError:\n    import pydantic\n"
        imported = {alias.name for node in _nodes(source) for alias in node.names}
        assert "pydantic" in imported

    def test_a_guarded_handler_body_still_does_not_count(self):
        """An optional-import guard stays optional, handler body included."""
        source = "try:\n    import nats\nexcept ImportError:\n    import fallback_shim\n"
        assert _nodes(source) == []
