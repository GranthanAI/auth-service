from typing import AsyncGenerator
import uuid
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models.user import User
from app.services.user_service import UserService

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session, committing on success or rolling back on error."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

async def get_current_user(
    db: AsyncSession = Depends(get_db),
    x_user_id: str | None = Header(None, alias="X-User-Id")
) -> User:
    """
    Temporary authentication dependency that extracts user ID from a header (X-User-Id).
    This acts as a placeholder until the JWT Token Verification module is fully implemented.
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials"
        )
    try:
        user_uuid = uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID format"
        )
    
    try:
        return await UserService.get_user_by_id(db, user_uuid)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
