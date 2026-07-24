import logging
import time
from redis.asyncio import Redis

logger = logging.getLogger("app.cache.jwt_blacklist")

class JWTBlacklist:
    _fallback_blacklist = {}  # jti -> expire_timestamp

    @classmethod
    async def blacklist_token(cls, jti: str, expires_in_seconds: int, redis: Redis | None = None) -> None:
        """
        Add a JTI (JWT ID) to the Redis blacklist with a TTL matching the token's remaining time-to-live.
        """
        if expires_in_seconds <= 0:
            return
            
        key = f"blacklist:{jti}"
        if redis:
            try:
                await redis.setex(key, expires_in_seconds, "1")
                logger.info(f"Blacklisted access token JTI '{jti}' in Redis for {expires_in_seconds}s")
                return
            except Exception as e:
                logger.error(f"Redis error blacklisting JTI: {e}")

        # In-Memory Fallback
        now = time.time()
        cls._fallback_blacklist[jti] = now + expires_in_seconds
        logger.info(f"Blacklisted access token JTI '{jti}' in Memory for {expires_in_seconds}s")

    @classmethod
    async def is_blacklisted(cls, jti: str, redis: Redis | None = None) -> bool:
        """
        Check if the JTI is blacklisted.
        """
        key = f"blacklist:{jti}"
        if redis:
            try:
                exists = await redis.exists(key)
                return exists > 0
            except Exception as e:
                logger.error(f"Redis error checking JTI blacklist: {e}")

        # In-Memory Fallback Check
        now = time.time()
        expire_time = cls._fallback_blacklist.get(jti)
        if expire_time:
            if now > expire_time:
                # Cleanup expired entry
                cls._fallback_blacklist.pop(jti, None)
                return False
            return True
        return False
