import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Cookie
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.api.schemas.session import SessionResponse
from app.services.session_service import SessionService

router = APIRouter(prefix="/auth/sessions", tags=["sessions"])

@router.get("", response_model=list[SessionResponse])
async def get_active_sessions(
    refresh_token: str | None = Cookie(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> list[SessionResponse]:
    """
    List all active device sessions for the authenticated user. `is_current` marks the
    session of this browser (from its refresh cookie).
    """
    sessions = await SessionRepository.get_active_by_user_id(db, current_user.id)
    current = await SessionService.current_session(db, current_user.id, refresh_token)
    return [
        SessionResponse.model_validate(s).model_copy(update={"is_current": current is not None and s.id == current.id})
        for s in sessions
    ]

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

    # End that device's session (token deleted, not marked revoked: see SessionService).
    await SessionService.end_session(db, session)
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
    Sign out device sessions of the user. With exclude_current=true this browser (its
    refresh cookie) stays signed in; otherwise every session is ended.
    """
    cookie = refresh_token if exclude_current else None
    ended = await SessionService.revoke_other_sessions(db, current_user.id, cookie)
    await db.commit()
    kept = exclude_current and await SessionService.current_session(db, current_user.id, refresh_token) is not None
    message = "All other sessions revoked successfully." if kept else "All sessions revoked successfully."
    return {"message": message, "sessions_ended": ended}
