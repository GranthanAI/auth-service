"""Rate limiting and login lockout: atomic counters, real client IP, per-(IP,email) lockout with backoff,
per-email ceiling, bounded in-memory fallback, and limits on the email-sending endpoints."""

import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db, get_redis
from app.api.routers import auth as auth_router
from app.cache.login_attempt_cache import LoginAttemptCache
from app.core.config import settings
from app.core.exceptions import IncorrectPasswordException
from app.security.rate_limiter import RedisRateLimiter, incr_with_expire
from app.security.ttl_store import BoundedTTLStore


@pytest.fixture
async def redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.flushall()
    await r.aclose()


@pytest.fixture(autouse=True)
def _reset_fallbacks():
    LoginAttemptCache._fallback.clear()
    RedisRateLimiter._fallback.clear()
    yield


# ── atomic counter ───────────────────────────────────────────────────────────

async def test_incr_with_expire_sets_ttl_in_the_same_step(redis):
    count, ttl = await incr_with_expire(redis, "k", 60)
    assert count == 1 and 0 < ttl <= 60
    assert await redis.ttl("k") > 0
    count, _ = await incr_with_expire(redis, "k", 60)
    assert count == 2


# ── bounded fallback store ───────────────────────────────────────────────────

def test_fallback_store_is_bounded_and_expires():
    store = BoundedTTLStore(max_entries=100)
    for i in range(1000):
        store.incr(f"ip-{i}", 60, now=1000.0)
    assert len(store) <= 100
    # Expired entries vanish and restart their window.
    store.incr("x", 10, now=1000.0)
    assert store.get("x", now=1011.0) is None
    assert store.incr("x", 10, now=1011.0)[0] == 1


# ── login lockout ────────────────────────────────────────────────────────────

async def test_lockout_is_per_ip_and_email_not_global(redis):
    for _ in range(settings.FAILED_LOGIN_LIMIT):
        await LoginAttemptCache.record_failure("203.0.113.1", "victim@example.com", redis=redis)
    assert await LoginAttemptCache.get_lockout_remaining("203.0.113.1", "victim@example.com", redis=redis) > 0
    # The legitimate owner on another IP is not locked out by the attacker.
    assert await LoginAttemptCache.get_lockout_remaining("198.51.100.9", "victim@example.com", redis=redis) == 0
    # Nor is the attacker's IP locked for a different account.
    assert await LoginAttemptCache.get_lockout_remaining("203.0.113.1", "other@example.com", redis=redis) == 0


async def test_lockout_backs_off_exponentially_up_to_the_cap(redis):
    limit, base = settings.FAILED_LOGIN_LIMIT, settings.LOCKOUT_BASE_SECONDS
    assert LoginAttemptCache.lock_seconds(limit - 1) == 0
    assert LoginAttemptCache.lock_seconds(limit) == base
    assert LoginAttemptCache.lock_seconds(limit + 1) == base * 2
    assert LoginAttemptCache.lock_seconds(limit + 2) == base * 4
    assert LoginAttemptCache.lock_seconds(limit + 40) == settings.LOCKOUT_DURATION_SECONDS


async def test_per_email_ceiling_locks_across_ips(redis, monkeypatch):
    monkeypatch.setattr(settings, "FAILED_LOGIN_EMAIL_CEILING", 8)
    # Spread failures over many IPs so no single (IP, email) pair reaches its own limit.
    for i in range(8):
        await LoginAttemptCache.record_failure(f"203.0.113.{i}", "victim@example.com", redis=redis)
    assert await LoginAttemptCache.get_lockout_remaining("198.51.100.9", "victim@example.com", redis=redis) > 0


async def test_success_resets_only_that_pair(redis):
    for _ in range(settings.FAILED_LOGIN_LIMIT):
        await LoginAttemptCache.record_failure("203.0.113.1", "a@example.com", redis=redis)
    await LoginAttemptCache.reset("203.0.113.1", "a@example.com", redis=redis)
    assert await LoginAttemptCache.get_lockout_remaining("203.0.113.1", "a@example.com", redis=redis) == 0


async def test_lockout_works_without_redis():
    for _ in range(settings.FAILED_LOGIN_LIMIT):
        await LoginAttemptCache.record_failure("203.0.113.1", "a@example.com", redis=None)
    assert await LoginAttemptCache.get_lockout_remaining("203.0.113.1", "a@example.com", redis=None) > 0
    assert await LoginAttemptCache.get_lockout_remaining("198.51.100.9", "a@example.com", redis=None) == 0


# ── HTTP level ───────────────────────────────────────────────────────────────

def _app(redis):
    app = FastAPI()
    app.include_router(auth_router.router)

    async def _db():
        yield None

    async def _redis():
        return redis

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = _redis
    return app


def test_login_lockout_returns_403_and_victim_ip_is_unaffected(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def bad_login(*a, **k):
        raise IncorrectPasswordException()

    monkeypatch.setattr(auth_router.AuthService, "login", bad_login)
    # Raise the IP rate limit so we exercise the lockout, not the 429.
    monkeypatch.setattr(RedisRateLimiter, "check_rate_limit", _noop)
    app = _app(redis)
    body = {"email": "victim@example.com", "password": "wrong-password"}

    attacker = TestClient(app, client=("203.0.113.1", 5000))
    statuses = [attacker.post("/auth/login", json=body).status_code for _ in range(settings.FAILED_LOGIN_LIMIT + 1)]
    assert statuses[: settings.FAILED_LOGIN_LIMIT] == [401] * settings.FAILED_LOGIN_LIMIT
    locked = attacker.post("/auth/login", json=body)
    assert locked.status_code == 403
    assert "locked out" in locked.json()["detail"]  # response shape unchanged: {"detail": str}
    assert int(locked.headers["Retry-After"]) > 0

    owner = TestClient(app, client=("198.51.100.9", 5000))
    assert owner.post("/auth/login", json=body).status_code == 401  # wrong password, but not locked out


async def _noop(*a, **k):
    return None


@pytest.mark.parametrize("path", ["/auth/forgot-password", "/auth/resend-verification"])
def test_email_endpoints_are_rate_limited_per_email_and_per_ip(monkeypatch, path):
    from app.services.password_reset_service import PasswordResetService
    from app.services.verification_service import VerificationService
    from app.core.exceptions import UserNotFoundException

    async def unknown(*a, **k):
        raise UserNotFoundException("x")

    monkeypatch.setattr(PasswordResetService, "request_password_reset", unknown)
    monkeypatch.setattr(VerificationService, "resend_verification", unknown)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app = _app(redis)
    client = TestClient(app, client=("203.0.113.1", 5000))

    # Per email: the 4th request for the same address is rejected even from a fresh IP budget.
    codes = [client.post(path, json={"email": "t@example.com"}).status_code for _ in range(settings.EMAIL_ENDPOINT_EMAIL_LIMIT + 1)]
    assert codes[-1] == 429 and 429 not in codes[:-1]
    assert int(client.post(path, json={"email": "t@example.com"}).headers["Retry-After"]) > 0

    # Per IP: many different addresses from one IP are eventually rejected.
    other = TestClient(app, client=("203.0.113.77", 5000))
    results = [other.post(path, json={"email": f"u{i}@example.com"}).status_code for i in range(settings.EMAIL_ENDPOINT_IP_LIMIT + 1)]
    assert results[-1] == 429
    # A different IP is unaffected.
    assert TestClient(app, client=("198.51.100.5", 5000)).post(path, json={"email": "fresh@example.com"}).status_code != 429
