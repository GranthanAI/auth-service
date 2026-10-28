from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.cache.redis import RedisClient
from app.events.producer import KafkaProducerClient
from app.workers.outbox_worker import OutboxWorker
from app.workers.email_worker import EmailWorker

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Lifespan hooks
    # 1. Start Redis connection pool
    await RedisClient.initialize()
    # 2. Start Kafka Producer connection
    await KafkaProducerClient.initialize()
    # 3. Start Background Outbox Polling worker loop
    await OutboxWorker.start()
    # 4. Start the transactional email dispatcher (fails fast if the email config is unsafe)
    await EmailWorker.start()
    
    yield
    
    # Shutdown Lifespan hooks
    # 1. Terminate Background Outbox Polling worker
    await EmailWorker.stop()
    await OutboxWorker.stop()
    # 2. Terminate Kafka connection
    await KafkaProducerClient.close()
    # 3. Disconnect Redis pool
    await RedisClient.close()
