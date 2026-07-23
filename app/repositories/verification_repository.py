import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_verification import EmailVerification

class VerificationRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: uuid.UUID,
        code: str,
        expires_at: datetime
    ) -> EmailVerification:
        db_verification = EmailVerification(
            user_id=user_id,
            verification_code=code,
            expires_at=expires_at
        )
        db.add(db_verification)
        await db.flush()
        return db_verification

    @staticmethod
    async def get_active_code(
        db: AsyncSession,
        user_id: uuid.UUID,
        code: str
    ) -> EmailVerification | None:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(EmailVerification)
            .where(
                EmailVerification.user_id == user_id,
                EmailVerification.verification_code == code,
                EmailVerification.used == False,
                EmailVerification.expires_at > now
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_latest_active_code(db: AsyncSession, user_id: uuid.UUID) -> EmailVerification | None:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(EmailVerification)
            .where(
                EmailVerification.user_id == user_id,
                EmailVerification.used == False,
                EmailVerification.expires_at > now
            )
            .order_by(EmailVerification.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_as_used(db: AsyncSession, verification_id: uuid.UUID) -> None:
        await db.execute(
            update(EmailVerification)
            .where(EmailVerification.id == verification_id)
            .values(used=True)
        )
        await db.flush()
