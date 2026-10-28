import hashlib
import logging
import time

from fastapi import Request, HTTPException, status
from redis.asyncio import Redis

from app.security.ttl_store import BoundedTTLStore

logger = logging.getLogger("app.security.rate_limiter")

# INCR + EXPIRE must be one atomic step: with two round trips a crash between them leaves a counter that never expires
# and locks the key out forever. Returns {count, ttl_seconds}.
_INCR_WITH_EXPIRE = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""


def client_ip(request: Request) -> str:
    """The real client address. Behind the gateway uvicorn runs with --proxy-headers and --forwarded-allow-ips, so
    ``request.client.host`` is already the X-Forwarded-For client when (and only when) the peer is a trusted proxy."""
    return request.client.host if request.client else "unknown_ip"


def subject_key(value: str) -> str:
    """Stable, non-reversible key fragment for user-supplied values (emails) so they never appear in Redis keys."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:32]


async def incr_with_expire(redis: Redis, key: str, window_seconds: int) -> tuple[int, int]:
    count, ttl = await redis.eval(_INCR_WITH_EXPIRE, 1, key, window_seconds)
    return int(count), int(ttl)


class RedisRateLimiter:
    _fallback = BoundedTTLStore(max_entries=10_000)

    @classmethod
    async def check_rate_limit(
        cls,
        request: Request,
        endpoint_name: str,
        limit: int = 10,
        window_seconds: int = 60,
        redis: Redis | None = None,
        subject: str | None = None,
    ) -> None:
        """
        Fixed-window rate limit on ``endpoint_name``. Keyed on the real client IP, or on ``subject`` (e.g. an email)
        when given. Raises HTTP 429 with Retry-After when the limit is exceeded.
        """
        ident = f"subject:{subject_key(subject)}" if subject is not None else f"ip:{client_ip(request)}"
        key = f"rate:{endpoint_name}:{ident}"

        count = retry_after = None
        if redis:
            try:
                count, retry_after = await incr_with_expire(redis, key, window_seconds)
            except Exception as e:
                logger.error(f"Redis rate limiter error: {e}")
        if count is None:
            count, expires_at = cls._fallback.incr(key, window_seconds)
            retry_after = max(1, int(expires_at - time.time()))

        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(max(1, retry_after or window_seconds))},
            )
