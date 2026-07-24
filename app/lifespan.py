from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.cache.redis import RedisClient
from app.events.producer import KafkaProducerClient
from app.workers.outbox_worker import OutboxWorker

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Lifespan hooks
    # 1. Start Redis connection pool
    await RedisClient.initialize()
    # 2. Start Kafka Producer connection
    await KafkaProducerClient.initialize()
    # 3. Start Background Outbox Polling worker loop
    await OutboxWorker.start()
    
    yield
    
    # Shutdown Lifespan hooks
    # 1. Terminate Background Outbox Polling worker
    await OutboxWorker.stop()
    # 2. Terminate Kafka connection
    await KafkaProducerClient.close()
    # 3. Disconnect Redis pool
    await RedisClient.close()
