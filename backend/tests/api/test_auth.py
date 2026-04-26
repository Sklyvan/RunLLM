"""Tests for the Supabase JWT verification dependency."""

from __future__ import annotations

import jwt
import pytest
from fastapi import HTTPException

from runllm.api.auth import verify_supabase_jwt
from runllm.config import Settings


def _settings(secret: str = "test-secret") -> Settings:
    return Settings(supabase_anon_key=secret)  # type: ignore[arg-type]


def test_verify_jwt_returns_claims_for_valid_token() -> None:
    settings = _settings("super-secret")
    token = jwt.encode(
        {"sub": "11111111-1111-1111-1111-111111111111", "email": "x@y.com"},
        "super-secret",
        algorithm="HS256",
    )
    claims = verify_supabase_jwt(token, settings)
    assert str(claims.sub) == "11111111-1111-1111-1111-111111111111"
    assert claims.email == "x@y.com"


def test_verify_jwt_rejects_invalid_signature() -> None:
    settings = _settings("good")
    bad_token = jwt.encode(
        {"sub": "11111111-1111-1111-1111-111111111111"}, "bad", algorithm="HS256"
    )
    with pytest.raises(HTTPException) as excinfo:
        verify_supabase_jwt(bad_token, settings)
    assert excinfo.value.status_code == 401


def test_verify_jwt_requires_sub_claim() -> None:
    settings = _settings("s")
    token = jwt.encode({"email": "x"}, "s", algorithm="HS256")
    with pytest.raises(HTTPException):
        verify_supabase_jwt(token, settings)
