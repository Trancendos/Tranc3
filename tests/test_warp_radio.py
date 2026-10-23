"""WarpRadioConfig — Icecast credentials must not fall back to a known default.

Icecast ships with "hackme" as its stock admin password. Making the value
configurable was necessary but did not close the risk: with a fallback default,
a deployment that simply never sets the variable still runs on the credential an
attacker tries first, and nothing reports it. These tests hold the fail-closed
behaviour down.

Env is manipulated through monkeypatch rather than os.environ directly: the
earlier version of this file deleted ICECAST_* outright and restored only what
it had set, so running it wiped any real value out of the session for every
later test.
"""

import pytest

from src.warp_radio.station import WarpRadioConfig


def test_unset_password_is_refused(monkeypatch):
    """The whole point: no env var must not silently mean "hackme"."""
    monkeypatch.delenv("ICECAST_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("TRANC3_WARP_RADIO_ALLOW_INSECURE", raising=False)

    with pytest.raises(ValueError, match="ICECAST_ADMIN_PASSWORD"):
        WarpRadioConfig()


def test_the_stock_password_is_refused_even_when_set_explicitly(monkeypatch):
    """Setting the variable is not the property that matters; setting it to
    something other than Icecast's own default is."""
    monkeypatch.setenv("ICECAST_ADMIN_PASSWORD", "hackme")
    monkeypatch.delenv("TRANC3_WARP_RADIO_ALLOW_INSECURE", raising=False)

    with pytest.raises(ValueError, match="hackme"):
        WarpRadioConfig()


def test_a_real_password_is_accepted(monkeypatch):
    monkeypatch.setenv("ICECAST_ADMIN_PASSWORD", "super-secret")
    monkeypatch.delenv("TRANC3_WARP_RADIO_ALLOW_INSECURE", raising=False)

    assert WarpRadioConfig().icecast_admin_password == "super-secret"


def test_url_and_the_non_secret_defaults_are_unchanged(monkeypatch):
    """The URL keeps an ordinary default -- it is not a credential."""
    monkeypatch.delenv("ICECAST_URL", raising=False)
    monkeypatch.setenv("ICECAST_ADMIN_PASSWORD", "super-secret")

    config = WarpRadioConfig()
    assert config.icecast_url == "http://localhost:8000"
    assert config.mount_point == "/stream"
    assert config.max_listeners == 100
    assert config.default_format == "mp3"
    assert config.default_bitrate == 128


def test_url_honours_its_env_var(monkeypatch):
    monkeypatch.setenv("ICECAST_URL", "http://my-secure-icecast:8000")
    monkeypatch.setenv("ICECAST_ADMIN_PASSWORD", "super-secret")

    assert WarpRadioConfig().icecast_url == "http://my-secure-icecast:8000"
