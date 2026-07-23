import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_reset import PasswordReset

class PasswordResetRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: uuid.UUID,
        reset_token: str,
        expires_at: datetime
    ) -> PasswordReset:
        db_reset = PasswordReset(
            user_id=user_id,
            reset_token=reset_token,
            expires_at=expires_at
        )
        db.add(db_reset)
        await db.flush()
        return db_reset

    @staticmethod
    async def get_active_token(db: AsyncSession, reset_token: str) -> PasswordReset | None:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(PasswordReset)
            .where(
                PasswordReset.reset_token == reset_token,
                PasswordReset.used == False,
                PasswordReset.expires_at > now
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_as_used(db: AsyncSession, reset_id: uuid.UUID) -> None:
        await db.execute(
            update(PasswordReset)
            .where(PasswordReset.id == reset_id)
            .values(used=True)
        )
        await db.flush()
