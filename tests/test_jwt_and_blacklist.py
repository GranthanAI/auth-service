"""Access-token validation and the logout blacklist (no database needed)."""

import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.cache.jwt_blacklist import JWTBlacklist
from app.core.config import settings
from app.security.jwt_manager import ACCESS_TOKEN_ISSUER, JWTManager


def _claims(**over):
    now = int(time.time())
    base = {
        "iss": ACCESS_TOKEN_ISSUER, "sub": str(uuid.uuid4()), "email": "a@example.com",
        "jti": str(uuid.uuid4()), "iat": now, "exp": now + 300,
    }
    base.update(over)
    return base


def _sign(claims, key=None, alg=None):
    return jwt.encode(claims, key or settings.JWT_SECRET_KEY, algorithm=alg or settings.JWT_ALGORITHM)


def test_valid_token_round_trips():
    token, jti = JWTManager.encode_access_token(uuid.uuid4(), "a@example.com", 300)
    claims = JWTManager.decode_access_token(token)
    assert claims and claims["jti"] == jti and claims["iss"] == ACCESS_TOKEN_ISSUER


def test_expired_token_is_rejected():
    assert JWTManager.decode_access_token(_sign(_claims(exp=int(time.time()) - 5))) is None


def test_wrong_signature_is_rejected():
    assert JWTManager.decode_access_token(_sign(_claims(), key="some-other-secret-key-32-bytes-long!!")) is None


def test_unsigned_alg_none_token_is_rejected():
    forged = jwt.encode(_claims(), key=None, algorithm="none")
    assert JWTManager.decode_access_token(forged) is None


def test_wrong_issuer_is_rejected():
    assert JWTManager.decode_access_token(_sign(_claims(iss="https://evil.example"))) is None


@pytest.mark.parametrize("missing", ["sub", "email", "jti", "exp", "iat", "iss"])
def test_token_missing_a_required_claim_is_rejected(missing):
    claims = _claims()
    claims.pop(missing)
    assert JWTManager.decode_access_token(_sign(claims)) is None


def test_garbage_is_rejected():
    assert JWTManager.decode_access_token("not.a.jwt") is None


async def test_blacklisted_jti_is_reported_revoked():
    jti = str(uuid.uuid4())
    assert await JWTBlacklist.is_blacklisted(jti) is False
    await JWTBlacklist.blacklist_token(jti, 60)
    assert await JWTBlacklist.is_blacklisted(jti) is True


async def test_blacklist_entry_expires_with_the_token():
    jti = str(uuid.uuid4())
    await JWTBlacklist.blacklist_token(jti, 1)
    JWTBlacklist._fallback_blacklist[jti] = time.time() - 1  # simulate the TTL elapsing
    assert await JWTBlacklist.is_blacklisted(jti) is False


async def test_already_expired_token_is_not_blacklisted():
    jti = str(uuid.uuid4())
    await JWTBlacklist.blacklist_token(jti, 0)
    assert await JWTBlacklist.is_blacklisted(jti) is False
