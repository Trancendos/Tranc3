"""SEC-012 — TateKing's ffmpeg input path had to come from somewhere contained.

`py/command-line-injection`, CodeQL security-severity **9.8**: the highest score
in the estate's SARIF, and the last of the three criticals SEC-009 could name
but not adjudicate.

`shell=False` and a list argv, so there is no shell to inject into. What is
injected is an *argument*, and the argument is the input file. `ClipIn.
file_path` is a free-form `Optional[str]` on a JSON body; it went to SQLite
unexamined and came back out as `ffmpeg -i <input_path>`. The only check between
the two was `Path(input_path).exists()` — a check that the attacker's chosen
file is *there*, which is the opposite of a containment check.

Every test here was run against the unfixed worker first. The containment cases
all passed the path straight through; they are regression tests only because
they failed before `_contained_media` existed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def tateking(tmp_path_factory, monkeypatch_module):
    """Import the worker with its data paths already pointed at a temp directory.

    The env vars are set BEFORE `exec_module`, not after. The worker resolves
    `DB_PATH` and `MEDIA_DIR` at import and calls `mkdir` on both, so assigning
    `module.MEDIA_DIR` afterwards was too late: importing it had already created
    `workers/tateking/data/media/` inside the checkout, on every run. A test
    that writes into the repository to prove a containment guard works is not a
    contained test. Reported by cubic on PR #1150.
    """
    media = tmp_path_factory.mktemp("media")
    db = tmp_path_factory.mktemp("db") / "tateking.db"
    monkeypatch_module.setenv("TATEKING_MEDIA_DIR", str(media))
    monkeypatch_module.setenv("TATEKING_DB_PATH", str(db))

    path = _ROOT / "workers" / "tateking" / "worker.py"
    spec = importlib.util.spec_from_file_location("tateking_worker_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert module.MEDIA_DIR == media, "the worker did not honour TATEKING_MEDIA_DIR"
    (media / "clip.mp4").write_bytes(b"not really a video")
    (media / "nested").mkdir()
    (media / "nested" / "b.mp4").write_bytes(b"also not")
    return module


@pytest.fixture(scope="module")
def monkeypatch_module():
    """`monkeypatch` is function-scoped; this fixture is module-scoped."""
    with pytest.MonkeyPatch.context() as patcher:
        yield patcher


class TestMediaContainment:
    @pytest.mark.parametrize(
        "raw",
        [
            "/etc/passwd",  # the demonstration case: absolute, outside, exists
            "/etc/shadow",
            "../../../../etc/passwd",  # relative traversal
            "..",
            "nested/../../escape.mp4",  # traversal through a legitimate prefix
            "",  # nothing at all
            "   ",
        ],
    )
    def test_a_path_outside_the_media_root_is_refused(self, tateking, raw):
        with pytest.raises((tateking.PathTraversalError, ValueError)):
            tateking._contained_media(raw)

    def test_a_relative_path_inside_the_root_resolves(self, tateking):
        got = tateking._contained_media("clip.mp4")
        assert got == (tateking.MEDIA_DIR / "clip.mp4").resolve()
        assert got.is_absolute(), "a resolved path is absolute, so argv can never start with '-'"

    def test_a_nested_relative_path_inside_the_root_resolves(self, tateking):
        got = tateking._contained_media("nested/b.mp4")
        assert got == (tateking.MEDIA_DIR / "nested" / "b.mp4").resolve()

    def test_an_absolute_path_already_inside_the_root_is_accepted(self, tateking):
        """The shape existing rows legitimately have.

        Refusing it would have made the guard a breaking change dressed as a
        security fix, so it is accepted and rewritten as relative before the
        join — and it still has to be inside the root to get that treatment.
        """
        absolute = str((tateking.MEDIA_DIR / "clip.mp4").resolve())
        assert tateking._contained_media(absolute) == Path(absolute)

    def test_the_media_root_itself_is_not_a_file(self, tateking):
        """`MEDIA_DIR` exists, so an `exists()` check would have waved it through.

        A directory reaching `ffmpeg -i` is not a traversal, but it is the same
        class of mistake: the guard has to say what the value may BE, not only
        where it may point.
        """
        with pytest.raises(tateking.PathTraversalError):
            tateking._contained_media(str(tateking.MEDIA_DIR.resolve()))

    def test_a_symlink_out_of_the_root_is_refused(self, tateking, tmp_path):
        """Planted inside the root, pointing outside it.

        `safe_join` resolves before comparing, which is why this is covered
        without a rule of its own — recorded here because "we use safe_join" is
        a claim, and this is the measurement behind it.
        """
        outside = tmp_path / "outside.mp4"
        outside.write_bytes(b"x")
        link = tateking.MEDIA_DIR / "sneaky.mp4"
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(outside)
        with pytest.raises(tateking.PathTraversalError):
            tateking._contained_media("sneaky.mp4")


class TestClipBoundary:
    """The end-to-end half, and the one that calibrates non-trivially.

    The unit tests above fail against the unfixed worker because
    `_contained_media` does not exist there — true, but a weak proof. These go
    through the HTTP API, where the unfixed worker answers **201 Created** to a
    clip whose `file_path` is `/etc/passwd` and then hands that path to
    `ffmpeg -i`. That is the finding, stated as a request and a response.
    """

    @pytest.fixture()
    def client(self, tateking):
        from fastapi.testclient import TestClient

        # No path patching here: the module fixture pointed DB_PATH at a temp
        # location before the import, so this only has to create the schema.
        tateking.init_db()
        secret = getattr(tateking, "INTERNAL_SECRET", "") or ""
        headers = {"X-Internal-Secret": secret} if secret else {}
        return TestClient(tateking.app, headers=headers)

    def test_a_clip_cannot_name_a_file_outside_the_media_root(self, client):
        r = client.post("/clips", json={"title": "exfil", "file_path": "/etc/passwd"})
        assert r.status_code == 400, f"/etc/passwd was accepted as a clip path ({r.status_code})"
        assert "media root" in r.text

    def test_a_clip_cannot_traverse_out_of_the_media_root(self, client):
        r = client.post("/clips", json={"title": "exfil", "file_path": "../../../../etc/passwd"})
        assert r.status_code == 400, f"traversal was accepted as a clip path ({r.status_code})"

    def test_a_clip_inside_the_media_root_is_still_accepted(self, client):
        """The half that must not break: containment is not a ban on clips."""
        r = client.post("/clips", json={"title": "fine", "file_path": "clip.mp4"})
        assert r.status_code in (200, 201), r.text

    def test_a_clip_with_no_file_path_is_still_accepted(self, client):
        """`file_path` is optional and stays optional — a clip may be URL-only."""
        r = client.post("/clips", json={"title": "url-only", "source_url": "https://x/y.mp4"})
        assert r.status_code in (200, 201), r.text
