import os

from src.warp_radio.station import WarpRadioConfig


def test_warp_radio_config_defaults():
    # Clear env vars if they exist
    if "ICECAST_URL" in os.environ:
        del os.environ["ICECAST_URL"]
    if "ICECAST_ADMIN_PASSWORD" in os.environ:
        del os.environ["ICECAST_ADMIN_PASSWORD"]

    config = WarpRadioConfig()
    assert config.icecast_url == "http://localhost:8000"
    assert config.icecast_admin_password == "hackme"
    assert config.mount_point == "/stream"
    assert config.max_listeners == 100
    assert config.default_format == "mp3"
    assert config.default_bitrate == 128


def test_warp_radio_config_env_vars():
    os.environ["ICECAST_URL"] = "http://my-secure-icecast:8000"
    os.environ["ICECAST_ADMIN_PASSWORD"] = "super-secret"

    config = WarpRadioConfig()
    assert config.icecast_url == "http://my-secure-icecast:8000"
    assert config.icecast_admin_password == "super-secret"

    # Cleanup
    del os.environ["ICECAST_URL"]
    del os.environ["ICECAST_ADMIN_PASSWORD"]
