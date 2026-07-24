import logging
import time
from fastapi import Request, HTTPException, status
from redis.asyncio import Redis

logger = logging.getLogger("app.security.rate_limiter")

class RedisRateLimiter:
    _fallback_rates = {}  # key -> (count, reset_timestamp)

    @classmethod
    async def check_rate_limit(
        cls,
        request: Request,
        endpoint_name: str,
        limit: int = 10,
        window_seconds: int = 60,
        redis: Redis | None = None
    ) -> None:
        """
        Checks rate limiting for the client's IP on a specified endpoint.
        Raises HTTP 429 Too Many Requests if the limit is exceeded.
        """
        ip = request.client.host if request.client else "unknown_ip"
        key = f"rate:{ip}:{endpoint_name}"
        
        if redis:
            try:
                count = await redis.incr(key)
                if count == 1:
                    await redis.expire(key, window_seconds)
                if count > limit:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Rate limit exceeded. Please try again later."
                    )
                return
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Redis rate limiter error: {e}")

        # In-Memory Fallback
        now = time.time()
        fallback_key = f"{ip}:{endpoint_name}"
        
        data = cls._fallback_rates.get(fallback_key)
        if not data or now > data[1]:
            # Start new window
            cls._fallback_rates[fallback_key] = (1, now + window_seconds)
            return

        count, reset_time = data
        if count >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later."
            )

        cls._fallback_rates[fallback_key] = (count + 1, reset_time)
