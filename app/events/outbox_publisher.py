from sqlalchemy.ext.asyncio import AsyncSession
from app.models.outbox import Outbox

class OutboxPublisher:
    @staticmethod
    async def queue_event(db: AsyncSession, event_type: str, payload: dict) -> None:
        """
        Record a serialized event payload into the outbox database table.
        This must be called within the same transaction context as the state changes.
        """
        db_entry = Outbox(
            event_type=event_type,
            payload=payload,
            processed=False
        )
        db.add(db_entry)
        # Note: We flush or rely on caller to commit the transaction block
        await db.flush()
