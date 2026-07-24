import json
import logging
from aiokafka import AIOKafkaProducer
from app.core.config import settings

logger = logging.getLogger("app.events.producer")

class KafkaProducerClient:
    _producer: AIOKafkaProducer | None = None

    @classmethod
    async def initialize(cls) -> None:
        """
        Start the global async AIOKafkaProducer.
        """
        if cls._producer is None:
            logger.info("Connecting to Kafka bootstrap servers...")
            try:
                cls._producer = AIOKafkaProducer(
                    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                    value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                    acks="all",
                    enable_idempotence=True,
                    compression_type="gzip",
                    linger_ms=settings.KAFKA_LINGER_MS
                )
                await cls._producer.start()
                logger.info("Kafka Producer started and connected successfully.")
            except Exception as e:
                logger.error(f"Could not connect to Kafka broker. Sandbox stub mode active. Error: {e}")
                cls._producer = None

    @classmethod
    async def send_event(cls, topic: str, key: str | None, value: dict) -> None:
        """
        Publish a serialized payload to the specified Kafka topic.
        """
        if cls._producer is None:
            # Sandbox console fallback logger
            logger.info(
                f"\n[DEV STUB LOG] =========================================\n"
                f"[DEV STUB LOG] Topic: {topic}\n"
                f"[DEV STUB LOG] Key: {key}\n"
                f"[DEV STUB LOG] Event Payload: {value}\n"
                f"[DEV STUB LOG] =========================================\n"
            )
            return
        
        try:
            kafka_key = key.encode("utf-8") if key else None
            await cls._producer.send_and_wait(topic, value=value, key=kafka_key)
        except Exception as e:
            logger.error(f"Error publishing message to Kafka topic '{topic}': {e}")
            raise e

    @classmethod
    async def close(cls) -> None:
        """
        Gracefully stop the Kafka connection.
        """
        if cls._producer is not None:
            logger.info("Closing Kafka Producer...")
            await cls._producer.stop()
            cls._producer = None
            logger.info("Kafka connection closed.")
