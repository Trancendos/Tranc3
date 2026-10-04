"""The OpenTelemetry lockstep check, driven from deliberately broken inputs.

`scripts/check_otel_lockstep.py` exists because renovate bumped the four core
OTel pins and left the five instrumentation pins behind, which is not a version
skew that degrades -- it is unsatisfiable, so pip installed nothing and the
whole test suite went offline for six days.

The check shipped without tests and a reviewer immediately found a hole in it:
its version pattern captured a prefix, so `1.45.0rc1` recorded as `1.45.0` and
a pre-release pinned against a release read as consistent. That is the same
near-miss the check exists to catch, inside the check. Hence these.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_otel_lockstep", REPO / "scripts" / "check_otel_lockstep.py"
)
check = importlib.util.module_from_spec(_spec)
sys.modules["check_otel_lockstep"] = check
_spec.loader.exec_module(check)


def _pins(text, tmp_path):
    f = tmp_path / "requirements.txt"
    f.write_text(text, encoding="utf-8")
    return check._pins(f)


# --- the whole version token, not a prefix ------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("opentelemetry-sdk==1.45.0", "1.45.0"),
        pytest.param("opentelemetry-sdk==1.45.0rc1", "1.45.0rc1", id="release candidate"),
        pytest.param("opentelemetry-sdk==1.45.0.post1", "1.45.0.post1", id="post release"),
        pytest.param("opentelemetry-sdk==1.45.0.dev0", "1.45.0.dev0", id="dev release"),
    ],
)
def test_the_full_version_token_is_captured(line, expected, tmp_path):
    """A prefix match made three distinct pins read as the same one."""
    core, _ = _pins(f"{line}\nopentelemetry-instrumentation-fastapi==0.66b0\n", tmp_path)
    assert core == {expected}


@pytest.mark.parametrize(
    "line",
    [
        pytest.param('opentelemetry-sdk==1.45.0 ; python_version >= "3.9"', id="marker"),
        pytest.param("opentelemetry-sdk==1.45.0  # pinned by hand", id="comment"),
        pytest.param("opentelemetry-sdk==1.45.0\t", id="trailing tab"),
    ],
)
def test_markers_and_comments_are_not_part_of_the_version(line, tmp_path):
    core, _ = _pins(f"{line}\n", tmp_path)
    assert core == {"1.45.0"}


def test_a_prerelease_does_not_read_as_its_release(tmp_path):
    """The near-miss the prefix match hid: rc1 is not the release."""
    rc, _ = _pins("opentelemetry-sdk==1.45.0rc1\n", tmp_path)
    release, _ = _pins("opentelemetry-sdk==1.45.0\n", tmp_path)
    assert rc != release


# --- which packages count ----------------------------------------------


def test_both_series_are_recognised(tmp_path):
    core, instrumentation = _pins(
        "opentelemetry-api==1.45.0\n"
        "opentelemetry-sdk==1.45.0\n"
        "opentelemetry-proto==1.45.0\n"
        "opentelemetry-exporter-otlp-proto-grpc==1.45.0\n"
        "opentelemetry-instrumentation-fastapi==0.66b0\n"
        "opentelemetry-instrumentation==0.66b0\n",
        tmp_path,
    )
    assert core == {"1.45.0"}
    assert instrumentation == {"0.66b0"}


def test_an_unrelated_package_is_not_counted(tmp_path):
    core, instrumentation = _pins("fastapi==0.120.0\nnumpy==2.4.6\n", tmp_path)
    assert core == set() and instrumentation == set()


def test_a_file_pinning_only_one_series_is_not_compared(tmp_path):
    """Half a pair is not a mismatch; there is nothing to be inconsistent with."""
    core, instrumentation = _pins("opentelemetry-api==1.45.0\n", tmp_path)
    assert core and not instrumentation


# --- the real tree -----------------------------------------------------


def test_the_committed_requirements_files_are_in_lockstep():
    assert check.main() == 0


def test_the_check_has_something_to_check():
    """An empty scope reports the same PASSED as a consistent estate."""
    files = check._requirements_files()
    assert len(files) > 1
    with_both = [p for p in files if all(check._pins(p))]
    assert with_both, "no file pins both series, so main() would have no reference"


# --- main(), against synthetic trees ------------------------------------
#
# Everything above exercises `_pins`. cubic pointed out that nothing
# exercised `main()` rejecting anything: the only call was against the real
# repository, which is consistent, so the gating half of the check was
# verified by hand once and never encoded. A manual verification is a check
# that has only ever passed.


def _tree(tmp_path, files, monkeypatch):
    """Point the check at a synthetic requirements tree."""
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(check, "ROOT", tmp_path)
    return tmp_path


CONSISTENT = "opentelemetry-sdk==1.45.0\nopentelemetry-instrumentation-fastapi==0.66b0\n"
MISMATCHED = "opentelemetry-sdk==1.45.0\nopentelemetry-instrumentation-fastapi==0.65b0\n"


def test_main_rejects_a_worker_file_that_mixes_the_series(tmp_path, monkeypatch, capsys):
    """The defect: four worker files kept the unsatisfiable pair."""
    _tree(
        tmp_path,
        {
            "requirements.txt": CONSISTENT,
            "workers/vrar3d/requirements.txt": MISMATCHED,
        },
        monkeypatch,
    )
    assert check.main() == 1
    out = capsys.readouterr().out
    assert "FAILED" in out
    assert "workers/vrar3d/requirements.txt" in out


def test_main_accepts_a_consistent_tree(tmp_path, monkeypatch):
    _tree(
        tmp_path,
        {
            "requirements.txt": CONSISTENT,
            "workers/a/requirements.txt": CONSISTENT,
            "workers/b/requirements-worker.txt": CONSISTENT,
        },
        monkeypatch,
    )
    assert check.main() == 0


def test_main_rejects_a_root_that_pins_two_versions_of_one_series(tmp_path, monkeypatch):
    """They ship as one release; two is a defect wherever it appears."""
    _tree(
        tmp_path,
        {
            "requirements.txt": "opentelemetry-sdk==1.45.0\n"
            "opentelemetry-api==1.44.0\n"
            "opentelemetry-instrumentation-fastapi==0.66b0\n"
        },
        monkeypatch,
    )
    assert check.main() == 1


def test_main_refuses_when_the_root_gives_no_reference_pair(tmp_path, monkeypatch, capsys):
    """No reference reports the same PASSED as a consistent estate."""
    _tree(tmp_path, {"requirements.txt": "fastapi==0.120.0\n"}, monkeypatch)
    assert check.main() == 1
    assert "no reference pair" in capsys.readouterr().out


def test_main_refuses_when_there_are_no_requirements_files(tmp_path, monkeypatch, capsys):
    """An empty scope is a defect, not a pass."""
    monkeypatch.setattr(check, "ROOT", tmp_path)
    assert check.main() == 1
    assert "nothing to assert" in capsys.readouterr().out


def test_main_ignores_a_file_pinning_only_one_series(tmp_path, monkeypatch):
    """Half a pair cannot be inconsistent with the root."""
    _tree(
        tmp_path,
        {
            "requirements.txt": CONSISTENT,
            "workers/c/requirements.txt": "opentelemetry-sdk==1.45.0\n",
        },
        monkeypatch,
    )
    assert check.main() == 0
