"""No module may write to the filesystem outside the repo when imported.

Nine tests in tests/test_workers_p5.py raised `PermissionError: [Errno 13]
Permission denied: '/app'` during collection — before a single assertion ran —
because three workers created their output directory at module level. That
works in the container and nowhere else. The directory is needed at first use,
not at import, and an import that cannot fail is worth more than a directory
made a few milliseconds earlier.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load():
    path = REPO / "scripts" / "check_import_time_filesystem.py"
    spec = importlib.util.spec_from_file_location("check_import_time_filesystem", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return _load()


class TestWhatCountsAsAnImportTimeWrite:
    def _scan(self, guard, tmp_path, source: str):
        path = tmp_path / "worker.py"
        path.write_text(source, encoding="utf-8")
        # scan_file reports paths relative to REPO, so run it on a file inside it.
        target = REPO / "logs" / "_import_write_probe.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
        try:
            return guard.scan_file(target)
        finally:
            target.unlink()

    def test_a_module_level_mkdir_on_an_absolute_default_is_reported(self, guard, tmp_path):
        """Calibrated: reporting nothing fails this. This is the exact defect."""
        found = self._scan(
            guard,
            tmp_path,
            "from pathlib import Path\nimport os\n"
            'D = Path(os.environ.get("D", "/app/renders"))\n'
            "D.mkdir(parents=True, exist_ok=True)\n",
        )
        assert len(found) == 1
        assert "/app/renders" in found[0]

    def test_a_repo_relative_write_is_not_reported(self, guard, tmp_path):
        """Calibrated: reporting every mkdir fails this.

        `Path(__file__).parent / "data"` resolves inside the checkout and
        works wherever the code does. Failing on it would make the gate noise
        and force a refactor that buys nothing.
        """
        found = self._scan(
            guard,
            tmp_path,
            "from pathlib import Path\n"
            'D = Path(__file__).parent / "data"\n'
            "D.mkdir(parents=True, exist_ok=True)\n",
        )
        assert found == []

    def test_a_write_inside_a_function_is_not_an_import_time_write(self, guard, tmp_path):
        """Calibrated: walking the whole tree fails this.

        Creating the directory at first use is the fix. A check that flagged
        it too would reject its own remedy.
        """
        found = self._scan(
            guard,
            tmp_path,
            "from pathlib import Path\n"
            'D = Path("/app/renders")\n'
            "def go():\n    D.mkdir(parents=True, exist_ok=True)\n",
        )
        assert found == []

    def test_a_write_under_a_module_level_if_still_counts(self, guard, tmp_path):
        """A conditional import-time write runs on the branch taken."""
        found = self._scan(
            guard,
            tmp_path,
            "from pathlib import Path\nimport os\n"
            'D = Path("/app/renders")\n'
            "if os.name:\n    D.mkdir(parents=True, exist_ok=True)\n",
        )
        assert len(found) == 1

    def test_the_environment_override_does_not_hide_the_default(self, guard, tmp_path):
        """The default is what runs where nobody sets the variable — CI."""
        found = self._scan(
            guard,
            tmp_path,
            "from pathlib import Path\nimport os\n"
            'D = Path(os.environ.get("DATA_DIR", "/data"))\n'
            "D.mkdir(parents=True, exist_ok=True)\n",
        )
        assert len(found) == 1
        assert "/data" in found[0]


class TestTheShapesItMustNotMiss:
    """Every way the estate can write at import, and one it must not flag."""

    def _scan(self, guard, source: str):
        target = REPO / "logs" / "_import_write_probe.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
        try:
            return guard.scan_file(target)
        finally:
            target.unlink()

    def test_a_literal_receiver_is_seen(self, guard):
        """Calibrated: resolving only named variables fails this.

        `Path("/app/renders").mkdir()` anchors on a call, not a name, so a
        scanner that looked up an assignment table found nothing and reported
        the file clean.
        """
        found = self._scan(guard, 'from pathlib import Path\nPath("/app/renders").mkdir()\n')
        assert len(found) == 1

    def test_a_class_body_write_is_seen(self, guard):
        """Calibrated: skipping ClassDef fails this.

        A class body executes on import exactly as module level does.
        Skipping it left a bypass that reads as perfectly ordinary code.
        """
        source = 'from pathlib import Path\nD = Path("/app/x")\nclass C:\n    D.mkdir()\n'
        assert len(self._scan(guard, source)) == 1

    def test_a_write_in_an_exception_handler_is_seen(self, guard):
        """Calibrated: walking only body/orelse/finalbody fails this."""
        source = (
            'from pathlib import Path\nD = Path("/app/y")\n'
            "try:\n    pass\nexcept OSError:\n    D.mkdir()\n"
        )
        assert len(self._scan(guard, source)) == 1

    def test_an_open_for_writing_is_seen(self, guard):
        """Calibrated: covering only pathlib methods fails this."""
        assert len(self._scan(guard, 'f = open("/app/z.txt", "w")\n')) == 1

    def test_an_open_inside_a_with_is_seen(self, guard):
        source = 'with open("/app/w.txt", "a") as fh:\n    pass\n'
        assert len(self._scan(guard, source)) == 1

    def test_an_open_for_reading_is_not_flagged(self, guard):
        """Calibrated: treating every open() as a write fails this.

        Reading a file at import is ordinary and harmless. Flagging it would
        make the gate noise, and noise is how a gate gets removed.
        """
        assert self._scan(guard, 'f = open("/app/r.txt")\n') == []

    def test_a_function_body_write_is_still_not_flagged(self, guard):
        """The remedy itself must not read as the defect."""
        source = 'from pathlib import Path\nD = Path("/app/q")\ndef go():\n    D.mkdir()\n'
        assert self._scan(guard, source) == []


class TestTheRatchet:
    def test_a_new_write_fails(self, guard, monkeypatch, tmp_path):
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps([]), encoding="utf-8")
        monkeypatch.setattr(guard, "BASELINE", baseline)
        monkeypatch.setattr(guard, "scan", lambda: ["workers/x/worker.py:1: mkdir /data"])
        assert guard.main([]) == 1

    def test_an_unrecorded_improvement_fails(self, guard, monkeypatch, tmp_path):
        """Calibrated: checking only for additions fails this.

        An improvement nobody records lets the next regression slip in under
        the old count — the same reasoning the flow baseline carries.
        """
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps(["workers/x/worker.py:1: mkdir /data"]), encoding="utf-8")
        monkeypatch.setattr(guard, "BASELINE", baseline)
        monkeypatch.setattr(guard, "scan", lambda: [])
        assert guard.main([]) == 1

    def test_a_missing_baseline_fails_rather_than_passes(self, guard, monkeypatch, tmp_path):
        monkeypatch.setattr(guard, "BASELINE", tmp_path / "absent.json")
        monkeypatch.setattr(guard, "scan", lambda: [])
        assert guard.main([]) == 1


class TestTheLiveTree:
    def test_the_estate_has_no_import_time_writes_left(self, guard):
        """The class is closed, not merely frozen.

        The baseline started at eight and is empty. That is the difference
        between a ratchet that holds a backlog and one that holds a fixed
        invariant — and it means a single new entry is unambiguous.
        """
        assert guard.scan() == []
        assert json.loads(guard.BASELINE.read_text(encoding="utf-8")) == []

    @pytest.mark.parametrize(
        ("worker", "env_var"),
        [
            ("workers/blender-worker/worker.py", "RENDERS_DIR"),
            ("workers/ffmpeg-worker/worker.py", "FFMPEG_WORKDIR"),
            ("workers/triposr-worker/worker.py", "OUTPUTS_DIR"),
        ],
    )
    def test_the_three_that_broke_ci_import_without_creating_anything(
        self, worker, env_var, monkeypatch, tmp_path
    ):
        """Calibrated: restoring the module-level mkdir fails this.

        Pointed at a directory that does not exist, the import must leave it
        not existing. Asserting only that the import returns would pass under
        the mutation — on this machine `/app` is creatable, which is exactly
        why the defect survived local runs and only showed up on the runner.
        """
        target = tmp_path / "not-created-yet"
        monkeypatch.setenv("INTERNAL_SECRET", "b" * 64)
        monkeypatch.setenv(env_var, str(target))
        path = REPO / worker
        spec = importlib.util.spec_from_file_location(f"probe_{path.parent.name}", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        assert not target.exists(), f"{worker} created {env_var} at import"
