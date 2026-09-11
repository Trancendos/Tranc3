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
    _module_files,
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


class TestTheThreeHolesThatLetRealBreaksThrough:
    """Each of these reported PASSED on a run that failed.

    Three consecutive Service Topology failures came through this check, in
    three different ways, and none of them had a test. They do now: the
    check exists to be the thing that notices, and being wrong three times
    without a regression pinning any of it is the same defect one level up.
    """

    def test_a_function_level_import_counts_for_a_script(self):
        """Calibrated: dropping `functions=True` for scripts fails this.

        `scripts/build_action_backlog.py` imports the routing registry from
        inside `_apply_routing`, on the unconditional path from `main()`.
        Skipping it reported PASSED on a job that died there. For a script
        the question is not "does it import" but "does it run".
        """
        source = "def go():\n    import aiohttp\n"
        assert _import_time_nodes(ast.parse(source).body, functions=True)

    def test_the_script_walk_reaches_a_function_level_dependency(self, tmp_path):
        """The mechanism, exercised through `external_imports` as callers use it."""
        script = tmp_path / "entry.py"
        script.write_text("def go():\n    import aiohttp\n", encoding="utf-8")
        assert "aiohttp" in external_imports(script, script=True)
        assert "aiohttp" not in external_imports(script)

    def test_main_walks_its_scripts_as_scripts(self, monkeypatch):
        """Calibrated: `main` passing the default fails this.

        The two tests above prove the mechanism works. Neither proves it is
        used — and a control that exists and is never invoked is the exact
        defect this check was written to catch, so leaving its own wiring
        unasserted would be the joke telling itself.
        """
        import scripts.check_ci_job_dependencies as checker

        seen: list[bool] = []
        real = checker.external_imports

        def record(entry, _seen=None, *, script=False):
            # Only the entry call — `external_imports` recurses through
            # itself for library modules, and those correctly pass the
            # default. It is the call `main` makes that must say script.
            if _seen is None:
                seen.append(script)
            return real(entry, _seen, script=script)

        monkeypatch.setattr(checker, "external_imports", record)
        checker.main(["--job", "topology"])
        assert seen and all(seen), "main() walked a script without script=True"

    def test_a_function_level_import_still_does_not_count_for_a_library(self):
        """The exemption survives where it was right: `src/event_bus/bus.py`
        imports httpx in a webhook branch a documentation render never
        reaches, and failing on that reports a break that cannot happen."""
        assert _nodes("def go():\n    import httpx\n") == []

    def test_a_handler_that_can_reraise_is_not_an_optional_dependency(self):
        """Calibrated: reading only the exception type fails this.

        The backlog generator swallows a missing `src` and re-raises
        everything else, so a missing `fastapi` propagates and the job dies.
        Counting that as a declared-optional dependency is how this check
        reported PASSED while CI was red.
        """
        reraises = ast.parse(
            "try:\n"
            "    import fastapi\n"
            "except ModuleNotFoundError as exc:\n"
            "    if exc.name != 'src':\n"
            "        raise\n"
        ).body[0]
        swallows = ast.parse(
            "try:\n    import fastapi\nexcept ModuleNotFoundError:\n    pass\n"
        ).body[0]
        assert _guarded(reraises.handlers) is False
        assert _guarded(swallows.handlers) is True

    def test_a_package_init_on_the_path_is_followed(self):
        """Calibrated: resolving only the leaf module fails this.

        Importing `src.observability.observatory` runs
        `src/observability/__init__.py` first, and that one imports
        `.health`, which imports aiohttp. Following only the leaf made the
        whole chain invisible — the third break, and the one that took two
        commits to find.
        """
        resolved = _module_files("src.observability.observatory")
        assert REPO / "src" / "observability" / "__init__.py" in resolved
        assert REPO / "src" / "observability" / "observatory.py" in resolved

    def test_a_type_checking_block_does_not_count(self):
        """`if TYPE_CHECKING:` is false at runtime, so its imports never run.

        Moving a heavyweight import there is the remedy; a check that cannot
        see the difference punishes the fix.
        """
        source = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import fastapi\n"
        names = [
            alias.name
            for node in _nodes(source)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        assert "fastapi" not in names

    def test_the_pure_validators_import_without_the_web_stack(self):
        """The break itself, as an invariant rather than an anecdote.

        `src/validation/primitives.py` exists so a CI script and a slim
        worker can validate input without dragging in FastAPI, aiohttp and
        structlog. Asserting it has no repository-external dependency at all
        is what stops the chain being reattached by a convenience import.
        """
        stdlib = set(sys.stdlib_module_names) | {"__future__"}
        assert external_imports(REPO / "src" / "validation" / "primitives.py") - stdlib == set()
