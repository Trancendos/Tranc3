"""api/auth.py must refuse to invent a credential when none is configured.

Until 2026-09-26 `_lookup_user` fell back to a hardcoded bcrypt hash of
"changeme" when DEMO_USER_HASH was unset, so a deployment that forgot the
variable shipped a working "admin" account whose password was a constant in a
public repository (#1228). Nothing in tests/ imported api.auth at all, which is
how a committed credential survived: the PR that introduced the fallback and
every PR after it ran a green suite that never looked.

These assert the direction the default fails in, which is the part that was
wrong. They are not a substitute for wiring api/core.py's create_app() into a
real application — see the note in _lookup_user about reachability.
"""

from __future__ import annotations

import importlib
import os

import pytest

_SKIP_REASON = None
try:  # pragma: no cover - exercised by which branch CI takes
    import fastapi  # noqa: F401
except ImportError as exc:  # pragma: no cover
    _SKIP_REASON = f"fastapi not installed: {exc}"

pytestmark = pytest.mark.skipif(_SKIP_REASON is not None, reason=_SKIP_REASON or "")

# The bcrypt hash that used to be the fallback. Kept here, and only here, so a
# regression that restores it is caught by name rather than by someone noticing.
_RETIRED_DEFAULT = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TgownFs9e1NmDOKWo2u4TbM6BVGU"


@pytest.fixture
def auth_module(monkeypatch):
    """Import api.auth with a JWT secret present; it hard-fails without one."""
    monkeypatch.setenv("JWT_SECRET", "test-secret-not-a-real-key")
    monkeypatch.delenv("DEMO_USER_HASH", raising=False)
    monkeypatch.delenv("DEMO_USER", raising=False)
    import api.auth as module

    return importlib.reload(module)


def test_no_user_when_no_hash_is_configured(auth_module, monkeypatch):
    monkeypatch.delenv("DEMO_USER_HASH", raising=False)
    assert auth_module._lookup_user("admin") is None


def test_empty_hash_is_treated_as_unconfigured(auth_module, monkeypatch):
    # An env var set to "" is a misconfiguration, not a configuration. bcrypt
    # would reject it anyway, but failing here keeps the refusal in one place.
    monkeypatch.setenv("DEMO_USER_HASH", "")
    assert auth_module._lookup_user("admin") is None


def test_configured_hash_yields_that_hash_and_nothing_else(auth_module, monkeypatch):
    monkeypatch.setenv("DEMO_USER_HASH", "$2b$12$" + "x" * 53)
    user = auth_module._lookup_user("admin")
    assert user is not None
    assert user["hashed_password"] == "$2b$12$" + "x" * 53
    assert auth_module._lookup_user("someone-else") is None


def test_the_retired_default_is_not_in_the_source(auth_module):
    # The fallback is gone from the module, not merely unreachable through it.
    source = os.path.join(os.path.dirname(auth_module.__file__), "auth.py")
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    occurrences = text.count(_RETIRED_DEFAULT)
    assert occurrences == 0, f"the retired default hash is back in {source}"
