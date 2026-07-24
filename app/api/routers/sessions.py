import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Cookie
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.services.refresh_token_service import RefreshTokenService
from app.api.schemas.session import SessionResponse

router = APIRouter(prefix="/auth/sessions", tags=["sessions"])

@router.get("", response_model=list[SessionResponse])
async def get_active_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> list[SessionResponse]:
    """
    List all active device sessions for the authenticated user.
    """
    sessions = await SessionRepository.get_active_by_user_id(db, current_user.id)
    return sessions  # type: ignore

@router.delete("/{session_id}", status_code=status.HTTP_200_OK)
async def revoke_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Revoke a specific device session. Forces a logout on that device.
    """
    session = await SessionRepository.get_by_id(db, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or unauthorized."
        )

    # Revoke the associated refresh token in DB
    await RefreshTokenRepository.revoke_by_id(db, session.refresh_token_id)
    
    # Delete the session record
    await SessionRepository.delete_by_id(db, session_id)
    await db.commit()
    
    return {"message": "Session revoked successfully."}

@router.delete("", status_code=status.HTTP_200_OK)
async def revoke_all_sessions(
    exclude_current: bool = False,
    refresh_token: str | None = Cookie(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Revoke all device sessions for the user.
    If exclude_current is true, the active browser session will not be revoked.
    """
    current_session = None
    if exclude_current and refresh_token:
        # Identify active session using refresh token cookie
        hashed_token = RefreshTokenService._hash_token(refresh_token)
        db_token = await RefreshTokenRepository.get_by_hash(db, hashed_token)
        if db_token and db_token.user_id == current_user.id:
            current_session = await SessionRepository.get_by_refresh_token_id(db, db_token.id)

    if current_session:
        # Revoke other refresh tokens
        all_sessions = await SessionRepository.get_active_by_user_id(db, current_user.id)
        for s in all_sessions:
            if s.id != current_session.id:
                await RefreshTokenRepository.revoke_by_id(db, s.refresh_token_id)
        
        # Delete other sessions
        await SessionRepository.delete_all_for_user_except_session(db, current_user.id, current_session.id)
        message = "All other sessions revoked successfully."
    else:
        # Revoke all tokens
        await RefreshTokenRepository.revoke_all_for_user(db, current_user.id)
        
        # Delete all sessions
        await SessionRepository.delete_all_for_user(db, current_user.id)
        message = "All sessions revoked successfully."

    await db.commit()
    return {"message": message}
