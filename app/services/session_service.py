import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.session_repository import SessionRepository
from app.services.refresh_token_service import RefreshTokenService


class SessionService:
    """Device sessions. A session is backed by one refresh token; revoking it makes that
    device unable to refresh, so it is signed out when its current access token expires
    (at most ACCESS_TOKEN_EXPIRE_MINUTES)."""

    @staticmethod
    async def current_session(db: AsyncSession, user_id: uuid.UUID, raw_refresh_token: str | None) -> Session | None:
        """The session behind the caller's refresh cookie, if it belongs to this user."""
        if not raw_refresh_token:
            return None
        db_token = await RefreshTokenRepository.get_by_hash(db, RefreshTokenService._hash_token(raw_refresh_token))
        if not db_token or db_token.user_id != user_id or db_token.revoked:
            return None
        return await SessionRepository.get_by_refresh_token_id(db, db_token.id)

    @staticmethod
    async def end_session(db: AsyncSession, session: Session) -> None:
        """Intentional sign-out of one device: its session and refresh token are removed.
        The token is deleted rather than marked revoked, so that device's next refresh is a
        plain 401 for that device only, not a "token reuse" that would end every session."""
        await SessionRepository.delete_by_id(db, session.id)
        await RefreshTokenRepository.delete_by_id(db, session.refresh_token_id)

    @staticmethod
    async def revoke_other_sessions(db: AsyncSession, user_id: uuid.UUID, raw_refresh_token: str | None) -> int:
        """Signs out every session of the user except the caller's own (identified by its
        refresh cookie); without a valid cookie every session is signed out. Returns the
        number of sessions ended. The caller commits."""
        current = await SessionService.current_session(db, user_id, raw_refresh_token)
        sessions = await SessionRepository.get_active_by_user_id(db, user_id)
        ended = 0
        for s in sessions:
            if current is not None and s.id == current.id:
                continue
            await SessionService.end_session(db, s)
            ended += 1
        return ended
