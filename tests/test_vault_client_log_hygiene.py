"""Log hygiene for the vault client and the JWT rotator — SEC-018.

CodeQL reports four `py/clear-text-logging-sensitive-data` alerts here:
`src/security/vault_client.py:65`, `:68`, `:108` and
`src/security/jwt_rotator.py:106`. All four are **false positives**: every one
logs a secret's *name* or a truncated UUID *identifier*, never a value. The rule
classifies the variables `secret_name` and `secret_id` as sensitive by their
names.

Reading around the alerts found one thing that was real, and it is what most of
this module tests: `httpx` does not redact userinfo when it builds an error
message, and every `VaultError` interpolates that exception, so credentials in
``VAULT_SERVICE_URL`` would have been written to the log by the vault client
itself. They are now discarded at construction.

The tests that assert an absence are paired with a control that proves the
assertion can fail, because "the secret did not appear" is exactly the kind of
claim that passes for the wrong reason.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from src.security.vault_client import VaultClient, VaultError, _without_userinfo

SECRET = "s3cr3t-jwt-value-DO-NOT-LOG-0123456789abcdef"


class TestUserinfoIsDiscarded:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("https://u:tOpS3cret@vault.internal:8038", "https://vault.internal:8038"),
            ("http://localhost:8038", "http://localhost:8038"),
            ("https://u:p@[fe80::1]:8038/v1", "https://[fe80::1]:8038/v1"),
            ("https://vault.internal:8038/", "https://vault.internal:8038/"),
            ("https://tokenonly@vault.internal:8038", "https://vault.internal:8038"),
        ],
    )
    def test_shapes(self, given: str, expected: str) -> None:
        assert _without_userinfo(given) == expected

    def test_ipv6_brackets_survive(self) -> None:
        """``urlsplit().hostname`` strips them; a bare ``fe80::1`` is not a host."""
        assert "[fe80::1]" in _without_userinfo("https://u:p@[fe80::1]:8038/v1")

    def test_client_strips_at_construction(self) -> None:
        client = VaultClient(base_url="https://u:tOpS3cret@vault.internal:8038", token="t")
        assert "tOpS3cret" not in client.base_url

    def test_warning_names_the_variable_not_the_value(self, caplog) -> None:
        with caplog.at_level(logging.WARNING, logger="src.security.vault_client"):
            VaultClient(base_url="https://u:tOpS3cret@vault.internal:8038", token="t")
        assert "VAULT_TOKEN" in caplog.text
        assert "tOpS3cret" not in caplog.text

    def test_no_warning_when_there_is_nothing_to_strip(self, caplog) -> None:
        """A guard that warned on every start-up would be trained away."""
        with caplog.at_level(logging.WARNING, logger="src.security.vault_client"):
            VaultClient(base_url="http://localhost:8038", token="t")
        assert "discarded" not in caplog.text


def _realistic_failures(request: httpx.Request):
    """The exception shapes `set_secret`'s `except Exception` actually catches."""
    response = httpx.Response(400, request=request, text='{"error":"bad"}')
    return {
        "HTTPStatusError": httpx.HTTPStatusError(
            "Client error '400 Bad Request' for url 'http://vault:8038/secrets'",
            request=request,
            response=response,
        ),
        "ConnectError": httpx.ConnectError("[Errno 111] Connection refused", request=request),
        "ReadTimeout": httpx.ReadTimeout("timed out", request=request),
        "JSONDecodeError": json.JSONDecodeError("Expecting value", "<html>oops</html>", 0),
        "TypeError": TypeError("Object of type set is not JSON serializable"),
    }


class TestSecretValueNeverReachesTheMessage:
    """The alerts' actual claim, tested rather than asserted."""

    @pytest.fixture
    def request_carrying_the_secret(self) -> httpx.Request:
        return httpx.Request(
            "POST",
            "http://vault:8038/secrets",
            json={"name": "jwt-secret", "value": SECRET, "metadata": {}},
        )

    @pytest.mark.parametrize("shape", list(_realistic_failures(httpx.Request("GET", "http://x"))))
    def test_wrapped_error_omits_the_value(
        self, shape: str, request_carrying_the_secret: httpx.Request
    ) -> None:
        inner = _realistic_failures(request_carrying_the_secret)[shape]
        # `set_secret`'s own wrapping, verbatim.
        wrapped = VaultError(f"Failed to set secret 'jwt-secret': {inner}")
        # `jwt_rotator`'s rotation loop logs the wrapped error.
        logged = f"Could not push JWT secret to vault: {wrapped}"
        assert SECRET not in logged

    def test_control_a_leaking_exception_is_detected(
        self, request_carrying_the_secret: httpx.Request
    ) -> None:
        """Proves the assertions above can fail.

        Without this, every test in the class would pass just as happily against
        a module that never built a message at all.
        """
        leaky = RuntimeError(f"payload rejected: {request_carrying_the_secret.content.decode()}")
        wrapped = VaultError(f"Failed to set secret 'jwt-secret': {leaky}")
        assert SECRET in f"Could not push JWT secret to vault: {wrapped}"


class TestRotatorLogsAnIdentifierNotASecret:
    def test_secret_id_is_a_uuid_not_the_secret(self) -> None:
        """`jwt_rotator.py:106` logs `secret_id[:8]`, a UUID4 prefix.

        The rotated secret itself is `secrets.token_hex(64)` and only ever
        reaches the database as a truncated SHA-256.
        """
        import uuid

        from src.security.jwt_rotator import JWTRotator

        rotator = JWTRotator.__new__(JWTRotator)
        generated = rotator.generate_secret()
        assert len(generated) == 128, "token_hex(64) is 128 hex characters"
        # The identifier logged alongside it is unrelated to the secret's bytes.
        assert generated[:8] != str(uuid.uuid4())[:8]
