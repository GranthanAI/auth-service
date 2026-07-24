import logging
from redis.asyncio import Redis, ConnectionPool
from app.core.config import settings

logger = logging.getLogger("app.cache.redis")

class RedisClient:
    pool: ConnectionPool | None = None
    client: Redis | None = None

    @classmethod
    async def initialize(cls) -> None:
        """
        Initialize the async Redis connection pool.
        """
        if cls.pool is None:
            logger.info("Initializing Redis connection pool...")
            try:
                cls.pool = ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)
                cls.client = Redis(connection_pool=cls.pool)
                # Verify connection
                await cls.client.ping()
                logger.info("Redis connected successfully.")
            except Exception as e:
                logger.error(f"Could not connect to Redis at {settings.REDIS_URL}. Stub fallback active. Error: {e}")
                cls.pool = None
                cls.client = None

    @classmethod
    async def get_client(cls) -> Redis | None:
        """
        Retrieve the active Redis client.
        """
        return cls.client

    @classmethod
    async def close(cls) -> None:
        """
        Close the Redis connection pool gracefully.
        """
        if cls.pool is not None:
            logger.info("Closing Redis connection pool...")
            await cls.pool.disconnect()
            cls.pool = None
            cls.client = None
            logger.info("Redis connection pool closed.")
