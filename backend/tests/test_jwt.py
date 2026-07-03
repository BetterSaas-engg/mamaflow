"""Tests for the app-session JWT helpers (Phase A auth foundation)."""

import jwt
import pytest

from api.auth.jwt import create_access_token, decode_access_token


def test_round_trip_carries_subject_and_email():
    token = create_access_token(subject="user-123", email="parent@example.com")
    claims = decode_access_token(token)

    assert claims["sub"] == "user-123"
    assert claims["email"] == "parent@example.com"


def test_expired_token_is_rejected():
    token = create_access_token(subject="user-123", email="p@x.com", expires_minutes=-1)

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_token_signed_with_other_secret_is_rejected():
    forged = jwt.encode({"sub": "user-123"}, "x" * 48, algorithm="HS256")

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(forged)


def test_garbage_token_is_rejected():
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("not-a-jwt")
