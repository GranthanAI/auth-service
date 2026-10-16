import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import InvalidTokenException, CompromiseDetectedException
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.session_repository import SessionRepository
from app.security.token_generator import TokenGenerator
from app.models.refresh_token import RefreshToken

class RefreshTokenService:
    @staticmethod
    def _hash_token(token: str) -> str:
        """Calculate the SHA-256 hash of the plain token."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    async def create_refresh_token(cls, db: AsyncSession, user_id: uuid.UUID) -> tuple[str, RefreshToken]:
        """
        Generate a new cryptographically secure refresh token,
        save its SHA-256 hash in the database, and return the plain token and db model.
        """
        plain_token = TokenGenerator.generate_secure_token()
        token_hash = cls._hash_token(plain_token)
        
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        db_token = await RefreshTokenRepository.create(db, user_id, token_hash, expires_at)
        return plain_token, db_token

    @classmethod
    async def rotate_refresh_token(
        cls,
        db: AsyncSession,
        raw_refresh_token: str
    ) -> tuple[str, RefreshToken, uuid.UUID]:
        """
        Rotates an existing refresh token. Enforces rotation rules and detects compromises.
        Returns: tuple of (new_raw_token, new_db_token, user_id)
        """
        token_hash = cls._hash_token(raw_refresh_token)
        db_token = await RefreshTokenRepository.get_by_hash(db, token_hash)
        
        if not db_token:
            raise InvalidTokenException("Invalid refresh token.")

        # Check expiration
        now = datetime.now(timezone.utc)
        # Ensure db_token.expires_at is timezone-aware
        expires_at = db_token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < now:
            # Token is expired, delete session and raise exception
            session = await SessionRepository.get_by_refresh_token_id(db, db_token.id)
            if session:
                await SessionRepository.delete_by_id(db, session.id)
            # The request is about to fail with an exception, which makes the
            # request-scoped session roll back; persist the cleanup first.
            await db.commit()
            raise InvalidTokenException("Refresh token has expired.")

        # COMPROMISE DETECTION: a token that is already revoked is being reused, and
        # so is one that loses the atomic claim below (a concurrent refresh with the
        # same token). Either way the whole family is revoked.
        # Claim first, atomically: revoking via a separate read-then-write would let
        # two simultaneous refreshes both pass the `revoked` check.
        claimed = False if db_token.revoked else await RefreshTokenRepository.claim_for_rotation(db, db_token.id)
        if not claimed:
            await RefreshTokenRepository.revoke_all_for_user(db, db_token.user_id)
            await SessionRepository.delete_all_for_user(db, db_token.user_id)
            # Commit before raising: the request-scoped session rolls back on any
            # exception, which would silently undo the revocation.
            await db.commit()
            raise CompromiseDetectedException()

        # Generate a new token
        new_plain_token, new_db_token = await cls.create_refresh_token(db, db_token.user_id)
        
        return new_plain_token, new_db_token, db_token.id

    @classmethod
    async def revoke_refresh_token(cls, db: AsyncSession, raw_refresh_token: str) -> None:
        """Revoke a refresh token by hashing it and updating its database status."""
        token_hash = cls._hash_token(raw_refresh_token)
        db_token = await RefreshTokenRepository.get_by_hash(db, token_hash)
        if db_token:
            await RefreshTokenRepository.revoke_by_id(db, db_token.id)
