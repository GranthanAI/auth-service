import logging
import time

from redis.asyncio import Redis

from app.core.config import settings
from app.security.rate_limiter import incr_with_expire, subject_key
from app.security.ttl_store import BoundedTTLStore

logger = logging.getLogger("app.cache.login_attempt_cache")


class LoginAttemptCache:
    """
    Brute-force protection for /auth/login.

    * Per (client IP, email): after FAILED_LOGIN_LIMIT failures the pair is locked for LOCKOUT_BASE_SECONDS, doubling
      with every further failure up to LOCKOUT_DURATION_SECONDS. Someone else hammering an account from another IP
      therefore cannot lock the legitimate owner out.
    * Per email (all IPs): a much higher ceiling (FAILED_LOGIN_EMAIL_CEILING) that still stops distributed guessing;
      reaching it locks the account for LOCKOUT_DURATION_SECONDS.
    """

    _fallback = BoundedTTLStore(max_entries=10_000)

    @staticmethod
    def _keys(ip: str, email: str) -> tuple[str, str, str, str]:
        h = subject_key(email)
        return (f"login_fail:pair:{ip}:{h}", f"login_lock:pair:{ip}:{h}",
                f"login_fail:email:{h}", f"login_lock:email:{h}")

    @staticmethod
    def lock_seconds(failures: int) -> int:
        """Exponential backoff for the (IP, email) pair; 0 below the limit."""
        over = failures - settings.FAILED_LOGIN_LIMIT
        if over < 0:
            return 0
        return min(settings.LOCKOUT_DURATION_SECONDS, settings.LOCKOUT_BASE_SECONDS * (2 ** min(over, 30)))

    @classmethod
    async def get_lockout_remaining(cls, ip: str, email: str, redis: Redis | None = None) -> int:
        """Seconds the caller must still wait (0 = not locked)."""
        _, pair_lock, _, email_lock = cls._keys(ip, email)
        remaining = 0
        if redis:
            try:
                for key in (pair_lock, email_lock):
                    ttl = int(await redis.ttl(key) or 0)
                    remaining = max(remaining, ttl if ttl > 0 else 0)
                return remaining
            except Exception as e:
                logger.error(f"Redis error reading lockout: {e}")
        now = time.time()
        for key in (pair_lock, email_lock):
            entry = cls._fallback.get(key, now)
            if entry:
                remaining = max(remaining, int(entry[1] - now) + 1)
        return remaining

    @classmethod
    async def record_failure(cls, ip: str, email: str, redis: Redis | None = None) -> int:
        """Count a failed attempt and apply any lock it triggers. Returns the (IP, email) failure count."""
        pair_fail, pair_lock, email_fail, email_lock = cls._keys(ip, email)
        window = settings.LOCKOUT_DURATION_SECONDS
        if redis:
            try:
                pair_count, _ = await incr_with_expire(redis, pair_fail, window)
                email_count, _ = await incr_with_expire(redis, email_fail, window)
                seconds = cls.lock_seconds(pair_count)
                if seconds:
                    await redis.set(pair_lock, "1", ex=seconds)
                if email_count >= settings.FAILED_LOGIN_EMAIL_CEILING:
                    await redis.set(email_lock, "1", ex=window)
                return pair_count
            except Exception as e:
                logger.error(f"Redis error recording failed login: {e}")
        now = time.time()
        pair_count, _ = cls._fallback.incr(pair_fail, window, now)
        email_count, _ = cls._fallback.incr(email_fail, window, now)
        seconds = cls.lock_seconds(pair_count)
        if seconds:
            cls._fallback.set(pair_lock, 1, now + seconds)
        if email_count >= settings.FAILED_LOGIN_EMAIL_CEILING:
            cls._fallback.set(email_lock, 1, now + window)
        return pair_count

    @classmethod
    async def reset(cls, ip: str, email: str, redis: Redis | None = None) -> None:
        """Clear this (IP, email) pair after a successful login. The per-email counter decays on its own."""
        pair_fail, pair_lock, _, _ = cls._keys(ip, email)
        if redis:
            try:
                await redis.delete(pair_fail, pair_lock)
                return
            except Exception as e:
                logger.error(f"Redis error resetting login attempts: {e}")
        cls._fallback.delete(pair_fail)
        cls._fallback.delete(pair_lock)
