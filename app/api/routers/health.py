from fastapi import APIRouter, Depends, status, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.cache.redis import RedisClient
from app.events.producer import KafkaProducerClient

router = APIRouter(prefix="/health", tags=["health"])

@router.get("", status_code=status.HTTP_200_OK)
async def check_health(
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Health check endpoint verifying database, Redis cache, and Kafka producer connectivity.
    Returns HTTP 503 Service Unavailable if any critical system (DB or Redis) fails.
    """
    is_healthy = True
    
    # 1. Verify PostgreSQL Database
    try:
        await db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {e}"
        is_healthy = False
        
    # 2. Verify Redis Cache
    redis_client = await RedisClient.get_client()
    if redis_client:
        try:
            await redis_client.ping()
            redis_status = "healthy"
        except Exception as e:
            redis_status = f"unhealthy: {e}"
            is_healthy = False
    else:
        redis_status = "unhealthy: pool connection offline"
        is_healthy = False
        
    # 3. Verify Kafka Producer
    if KafkaProducerClient._producer is not None:
        kafka_status = "healthy"
    else:
        kafka_status = "unhealthy: connection offline (stub mode console logger active)"

    # Handle unhealthy dependencies
    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        
    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "services": {
            "database": db_status,
            "redis": redis_status,
            "kafka": kafka_status
        }
    }
