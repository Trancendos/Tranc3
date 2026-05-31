import datetime

import jwt
import pytest
from fastapi import HTTPException

import auth


def test_token_manager_signs_with_jwt_secret(monkeypatch):
    jwt_secret = "j" * 32
    legacy_secret = "s" * 32
    monkeypatch.setenv("JWT_SECRET", jwt_secret)
    monkeypatch.setenv("SECRET_KEY", legacy_secret)

    token = auth.token_manager.create_access_token({"sub": "alice"})

    payload = jwt.decode(token, jwt_secret, algorithms=[auth.ALGORITHM])
    assert payload["sub"] == "alice"

    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(token, legacy_secret, algorithms=[auth.ALGORITHM])


def test_token_manager_rejects_tokens_signed_with_secret_key(monkeypatch):
    jwt_secret = "j" * 32
    legacy_secret = "s" * 32
    monkeypatch.setenv("JWT_SECRET", jwt_secret)
    monkeypatch.setenv("SECRET_KEY", legacy_secret)
    token = jwt.encode(
        {
            "sub": "alice",
            "type": "access",
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5),
        },
        legacy_secret,
        algorithm=auth.ALGORITHM,
    )

    with pytest.raises(HTTPException, match="Invalid token"):
        auth.token_manager.decode_token(token)


def test_token_manager_fails_closed_without_jwt_secret_in_production(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        auth.token_manager.create_access_token({"sub": "alice"})
