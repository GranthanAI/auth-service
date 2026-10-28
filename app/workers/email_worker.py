import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.db.session import async_session
from app.email.sender import EmailSender, get_email_sender
from app.email.templates import render
from app.models.email_outbox import EmailOutbox

logger = logging.getLogger("app.workers.email_worker")


def backoff_seconds(attempts: int) -> int:
    """Delay before retry number ``attempts`` (1-based): base * 2^(attempts-1), capped."""
    return min(settings.EMAIL_RETRY_MAX_SECONDS, settings.EMAIL_RETRY_BASE_SECONDS * (2 ** max(0, attempts - 1)))


class EmailWorker:
    _running = False
    _task: asyncio.Task | None = None
    _sender: EmailSender | None = None

    @classmethod
    async def start(cls) -> None:
        if not cls._running:
            cls._sender = get_email_sender()  # fails fast on an unsafe configuration
            cls._running = True
            cls._task = asyncio.create_task(cls._poll_loop())
            logger.info("Email worker started.")

    @classmethod
    async def stop(cls) -> None:
        if cls._running:
            cls._running = False
            if cls._task:
                cls._task.cancel()
                try:
                    await cls._task
                except asyncio.CancelledError:
                    pass
            logger.info("Email worker stopped.")

    @classmethod
    async def _poll_loop(cls) -> None:
        while cls._running:
            try:
                handled = await cls.process_batch(cls._sender)
            except Exception as e:  # keep the daemon alive; never log row contents
                logger.error("Error in email worker loop: %s", type(e).__name__)
                handled = 0
            if handled == 0:
                await asyncio.sleep(settings.EMAIL_WORKER_POLL_INTERVAL_SECONDS)

    @classmethod
    async def process_batch(cls, sender: EmailSender, session_factory=None) -> int:
        """Process up to EMAIL_BATCH_SIZE due rows, one transaction each. Returns the number handled."""
        handled = 0
        for _ in range(settings.EMAIL_BATCH_SIZE):
            if not await cls._process_one(sender, session_factory or async_session):
                break
            handled += 1
        return handled

    @classmethod
    async def _process_one(cls, sender: EmailSender, session_factory) -> bool:
        # One row per transaction: a commit releases every row lock taken by the SELECT, so batching several rows in
        # one transaction would let a second worker pick up rows this one is still sending.
        async with session_factory() as db:
            now = datetime.now(timezone.utc)
            row = (await db.execute(
                select(EmailOutbox)
                .where(EmailOutbox.next_attempt_at <= now)
                .order_by(EmailOutbox.next_attempt_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )).scalar_one_or_none()
            if row is None:
                return False
            try:
                await sender.send(render(row.kind, row.to_email, row.payload))
                await db.delete(row)  # delivered: the secret must not outlive the send
            except Exception as e:
                row.attempts += 1
                row.last_error = type(e).__name__[:100]
                if row.attempts >= settings.EMAIL_MAX_ATTEMPTS:
                    logger.error("Giving up on email %s (%s) after %d attempts: %s",
                                 row.id, row.kind, row.attempts, row.last_error)
                    await db.delete(row)  # drop the secret rather than keep it forever
                else:
                    row.next_attempt_at = now + timedelta(seconds=backoff_seconds(row.attempts))
                    logger.warning("Email %s (%s) failed (attempt %d): %s",
                                   row.id, row.kind, row.attempts, row.last_error)
            await db.commit()
            return True
