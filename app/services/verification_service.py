import uuid
import secrets
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserStatus
from app.core.config import settings
from app.core.exceptions import AuthServiceException, UserNotFoundException
from app.repositories.user_repository import UserRepository
from app.repositories.verification_repository import VerificationRepository

from app.events.outbox_publisher import OutboxPublisher
from app.events.auth_events import EmailVerifiedEvent

class VerificationService:
    @staticmethod
    async def create_verification_code(db: AsyncSession, user_id: uuid.UUID) -> str:
        """
        Generate a cryptographically secure 6-digit numeric verification OTP,
        persist it, print it to the console (developer log), and return it.
        """
        code = str(secrets.randbelow(900000) + 100000)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
        
        await VerificationRepository.create(db, user_id, code, expires_at)
        
        print(f"\n[DEV MODE] =========================================")
        print(f"[DEV MODE] Verification OTP for user {user_id}: {code}")
        print(f"[DEV MODE] =========================================\n")
        
        return code

    @classmethod
    async def verify_email_code(cls, db: AsyncSession, email: str, code: str) -> None:
        """
        Verify the OTP code, mark it as used, and set the user account to ACTIVE status.
        """
        user = await UserRepository.get_by_email(db, email)
        if not user:
            raise UserNotFoundException(email)
        
        if user.status == UserStatus.ACTIVE:
            raise AuthServiceException("Email address is already verified.")

        active_code = await VerificationRepository.get_active_code(db, user.id, code)
        if not active_code:
            raise AuthServiceException("Invalid or expired verification code.")

        # Mark OTP as used
        await VerificationRepository.mark_as_used(db, active_code.id)

        # Activate user account
        await UserRepository.update(
            db,
            user,
            {
                "is_email_verified": True,
                "status": UserStatus.ACTIVE
            }
        )

        # Transactionally queue EmailVerified outbox event
        event = EmailVerifiedEvent(
            user_id=user.id,
            email=user.email
        )
        await OutboxPublisher.queue_event(db, "EmailVerified", event.model_dump(mode="json"))

    @classmethod
    async def resend_verification(cls, db: AsyncSession, email: str) -> None:
        """
        Invalidate existing codes and issue a new verification code.
        """
        user = await UserRepository.get_by_email(db, email)
        if not user:
            raise UserNotFoundException(email)
        
        if user.status == UserStatus.ACTIVE:
            raise AuthServiceException("Email address is already verified.")

        # Invalidate latest active code if exists
        latest_code = await VerificationRepository.get_latest_active_code(db, user.id)
        if latest_code:
            await VerificationRepository.mark_as_used(db, latest_code.id)

        # Issue new code
        await cls.create_verification_code(db, user.id)
