import uuid
from datetime import datetime
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session

class SessionRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: uuid.UUID,
        refresh_token_id: uuid.UUID,
        device: str | None,
        browser: str | None,
        os: str | None,
        ip_address: str | None,
        expires_at: datetime
    ) -> Session:
        db_session = Session(
            user_id=user_id,
            refresh_token_id=refresh_token_id,
            device=device,
            browser=browser,
            os=os,
            ip_address=ip_address,
            expires_at=expires_at
        )
        db.add(db_session)
        await db.flush()
        return db_session

    @staticmethod
    async def get_by_refresh_token_id(db: AsyncSession, refresh_token_id: uuid.UUID) -> Session | None:
        result = await db.execute(
            select(Session).where(Session.refresh_token_id == refresh_token_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, session_id: uuid.UUID) -> Session | None:
        result = await db.execute(
            select(Session).where(Session.id == session_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_by_id(db: AsyncSession, session_id: uuid.UUID) -> None:
        await db.execute(
            delete(Session).where(Session.id == session_id)
        )
        await db.flush()

    @staticmethod
    async def delete_all_for_user(db: AsyncSession, user_id: uuid.UUID) -> None:
        await db.execute(
            delete(Session).where(Session.user_id == user_id)
        )
        await db.flush()

    @staticmethod
    async def get_active_by_user_id(db: AsyncSession, user_id: uuid.UUID) -> list[Session]:
        result = await db.execute(
            select(Session).where(Session.user_id == user_id).order_by(Session.last_seen.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def delete_all_for_user_except_session(
        db: AsyncSession,
        user_id: uuid.UUID,
        exclude_session_id: uuid.UUID
    ) -> None:
        await db.execute(
            delete(Session).where(
                Session.user_id == user_id,
                Session.id != exclude_session_id
            )
        )
        await db.flush()

