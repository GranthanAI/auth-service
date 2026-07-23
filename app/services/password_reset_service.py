import uuid
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserStatus
from app.core.exceptions import AuthServiceException, UserNotFoundException, SamePasswordException
from app.repositories.user_repository import UserRepository
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.session_repository import SessionRepository
from app.security.password_hasher import PasswordHasher
from app.security.validators import validate_password_strength

class PasswordResetService:
    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    async def request_password_reset(cls, db: AsyncSession, email: str) -> str:
        """
        Generate a secure recovery token, save its SHA-256 hash in PostgreSQL, 
        print the raw token to the console (developer log), and return it.
        """
        user = await UserRepository.get_by_email(db, email)
        if not user:
            raise UserNotFoundException(email)

        raw_token = secrets.token_urlsafe(32)
        token_hash = cls._hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        await PasswordResetRepository.create(db, user.id, token_hash, expires_at)

        # Log to terminal console in Development Mode
        print(f"\n[DEV MODE] =========================================")
        print(f"[DEV MODE] Password Reset Token for user {user.id}: {raw_token}")
        print(f"[DEV MODE] =========================================\n")

        return raw_token

    @classmethod
    async def reset_password(cls, db: AsyncSession, raw_token: str, new_password: str) -> None:
        """
        Validate reset token, hash and update the password, mark the token as used, 
        and force log out all active user sessions for security.
        """
        token_hash = cls._hash_token(raw_token)
        active_reset = await PasswordResetRepository.get_active_token(db, token_hash)
        
        if not active_reset:
            raise AuthServiceException("Invalid or expired password reset token.")

        user = await UserRepository.get_by_id(db, active_reset.user_id)
        if not user:
            raise UserNotFoundException(str(active_reset.user_id))

        # Validate complexity constraints
        validate_password_strength(new_password)

        # Mismatch check to avoid same password
        if PasswordHasher.verify(user.password_hash, new_password):
            raise SamePasswordException()

        # Hash new password
        new_password_hash = PasswordHasher.hash(new_password)

        # Update password
        await UserRepository.update(db, user, {"password_hash": new_password_hash})

        # Mark token as used
        await PasswordResetRepository.mark_as_used(db, active_reset.id)

        # Revoke all tokens and delete all sessions (Security Invalidation)
        await RefreshTokenRepository.revoke_all_for_user(db, user.id)
        await SessionRepository.delete_all_for_user(db, user.id)
