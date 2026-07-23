from typing import AsyncGenerator
import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models.user import User
from app.services.user_service import UserService
from app.security.jwt_manager import JWTManager
from app.core.enums import UserStatus

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session, committing on success or rolling back on error."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

# OAuth2 scheme handler using Bearer Tokens
oauth2_scheme = HTTPBearer()

async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token_credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme)
) -> User:
    """
    Decodes and validates the JWT access token from the Authorization header.
    Returns the authenticated User model instance.
    """
    token = token_credentials.credentials
    payload = JWTManager.decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject format.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user = await UserService.get_user_by_id(db, user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account associated with this token does not exist.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or suspended.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
