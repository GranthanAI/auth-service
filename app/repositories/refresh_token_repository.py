import uuid
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken

class RefreshTokenRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime
    ) -> RefreshToken:
        db_token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at
        )
        db.add(db_token)
        await db.flush()
        return db_token

    @staticmethod
    async def get_by_hash(db: AsyncSession, token_hash: str) -> RefreshToken | None:
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def revoke_by_id(db: AsyncSession, token_id: uuid.UUID) -> None:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.id == token_id)
            .values(revoked=True)
        )
        await db.flush()

    @staticmethod
    async def claim_for_rotation(db: AsyncSession, token_id: uuid.UUID) -> bool:
        """Atomically mark a still-valid token revoked. Returns True only for the
        single caller that flipped it; any concurrent or later caller gets False.

        The check and the write are one conditional UPDATE, so two simultaneous
        refreshes with the same token cannot both succeed (the second blocks on
        the row lock, then re-evaluates `revoked = false` and matches nothing).
        """
        result = await db.execute(
            update(RefreshToken)
            .where(RefreshToken.id == token_id, RefreshToken.revoked.is_(False))
            .values(revoked=True)
        )
        await db.flush()
        return result.rowcount == 1

    @staticmethod
    async def revoke_all_for_user(db: AsyncSession, user_id: uuid.UUID) -> None:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .values(revoked=True)
        )
        await db.flush()
