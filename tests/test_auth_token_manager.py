import jwt
import pytest

import auth

# auth.py re-exports from src/auth/facade.py, which hardcodes HS256 internally
# (no public ALGORITHM constant is exported — see src/auth/facade.py::_ALGORITHM).
_ALGORITHM = "HS256"


def test_create_token_signs_with_jwt_secret(monkeypatch):
    jwt_secret = "j" * 32
    legacy_secret = "s" * 32
    monkeypatch.setenv("JWT_SECRET", jwt_secret)
    monkeypatch.setenv("SECRET_KEY", legacy_secret)

    token = auth.create_token(user_id="1", username="alice")

    payload = jwt.decode(token, jwt_secret, algorithms=[_ALGORITHM])
    assert payload["username"] == "alice"

    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(token, legacy_secret, algorithms=[_ALGORITHM])


def test_verify_token_rejects_tokens_signed_with_wrong_secret(monkeypatch):
    jwt_secret = "j" * 32
    legacy_secret = "s" * 32
    monkeypatch.setenv("JWT_SECRET", jwt_secret)
    monkeypatch.setenv("SECRET_KEY", legacy_secret)

    token = jwt.encode({"sub": "alice", "username": "alice"}, legacy_secret, algorithm=_ALGORITHM)

    # verify_token fails closed by returning None rather than raising —
    # see src/auth/tokens.py::decode_access_token.
    assert auth.verify_token(token) is None


def test_create_token_fails_closed_without_jwt_secret_in_production(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        auth.create_token(user_id="1", username="alice")
