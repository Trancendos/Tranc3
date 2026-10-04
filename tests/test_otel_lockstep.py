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
