import asyncio
import logging
from sqlalchemy import select
from app.db.session import async_session
from app.models.outbox import Outbox
from app.events.producer import KafkaProducerClient
from app.events.topics import USER_EVENTS_TOPIC
from app.core.config import settings

logger = logging.getLogger("app.workers.outbox_worker")

class OutboxWorker:
    _running = False
    _task = None

    @classmethod
    async def start(cls) -> None:
        """
        Start the background polling worker process.
        """
        if not cls._running:
            cls._running = True
            cls._task = asyncio.create_task(cls._poll_loop())
            logger.info("Outbox Worker daemon started.")

    @classmethod
    async def stop(cls) -> None:
        """
        Gracefully stop the background worker process.
        """
        if cls._running:
            cls._running = False
            if cls._task:
                cls._task.cancel()
                try:
                    await cls._task
                except asyncio.CancelledError:
                    pass
            logger.info("Outbox Worker daemon stopped.")

    @classmethod
    async def _poll_loop(cls) -> None:
        while cls._running:
            try:
                await cls._process_outbox()
            except Exception as e:
                logger.error(f"Error encountered in outbox worker loop: {e}")
            await asyncio.sleep(settings.OUTBOX_POLL_INTERVAL_SECONDS)  # Scan table using configured interval

    @classmethod
    async def _process_outbox(cls) -> None:
        async with async_session() as db:
            try:
                # Select unprocessed events up to OUTBOX_BATCH_SIZE
                result = await db.execute(
                    select(Outbox)
                    .where(Outbox.processed == False)
                    .order_by(Outbox.created_at.asc())
                    .limit(settings.OUTBOX_BATCH_SIZE)
                    .with_for_update(skip_locked=True)
                )
                events = list(result.scalars().all())
                
                if not events:
                    return

                logger.info(f"Outbox worker polling found {len(events)} unprocessed events.")
                
                for event in events:
                    try:
                        # Publish event payload to Kafka topic
                        await KafkaProducerClient.send_event(
                            topic=USER_EVENTS_TOPIC,
                            key=str(event.id),
                            value={
                                "event_type": event.event_type,
                                "payload": event.payload,
                                "created_at": event.created_at.isoformat()
                            }
                        )
                        # Set to processed on successful send/log
                        event.processed = True
                    except Exception as e:
                        logger.error(f"Failed to publish outbox event {event.id} to Kafka: {e}")
                
                await db.commit()
            except Exception as e:
                await db.rollback()
                raise e
