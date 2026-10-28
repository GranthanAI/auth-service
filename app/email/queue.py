from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_outbox import EmailOutbox


class EmailQueue:
    @staticmethod
    async def enqueue(db: AsyncSession, kind: str, to_email: str, payload: dict) -> None:
        """Queue an email in the caller's transaction, so it is sent if and only if the state change commits."""
        db.add(EmailOutbox(kind=kind, to_email=to_email, payload=payload))
        await db.flush()
