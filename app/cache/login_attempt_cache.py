import logging
from redis.asyncio import Redis
from app.core.config import settings

logger = logging.getLogger("app.cache.login_attempt_cache")

class LoginAttemptCache:
    _fallback_attempts = {}  # email -> count

    @classmethod
    async def increment_failed_attempts(cls, email: str, redis: Redis | None = None) -> int:
        """
        Increment the failed login attempt counter for the given email.
        The counter expires in LOCKOUT_DURATION_SECONDS.
        """
        key = f"failed_attempts:{email.lower()}"
        
        if redis:
            try:
                count = await redis.incr(key)
                if count == 1:
                    await redis.expire(key, settings.LOCKOUT_DURATION_SECONDS)
                return count
            except Exception as e:
                logger.error(f"Redis error incrementing attempts: {e}")

        # In-Memory fallback
        email_key = email.lower()
        count = cls._fallback_attempts.get(email_key, 0) + 1
        cls._fallback_attempts[email_key] = count
        return count

    @classmethod
    async def get_failed_attempts(cls, email: str, redis: Redis | None = None) -> int:
        """
        Get the current failed login attempt counter.
        """
        key = f"failed_attempts:{email.lower()}"
        
        if redis:
            try:
                val = await redis.get(key)
                return int(val) if val else 0
            except Exception as e:
                logger.error(f"Redis error getting attempts: {e}")
                
        return cls._fallback_attempts.get(email.lower(), 0)

    @classmethod
    async def reset_failed_attempts(cls, email: str, redis: Redis | None = None) -> None:
        """
        Clear the failed login counter (e.g. on successful login).
        """
        key = f"failed_attempts:{email.lower()}"
        
        if redis:
            try:
                await redis.delete(key)
                return
            except Exception as e:
                logger.error(f"Redis error deleting attempts: {e}")

        cls._fallback_attempts.pop(email.lower(), None)
