import uuid
import secrets
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserStatus
from app.core.config import settings
from app.core.exceptions import AuthServiceException, UserNotFoundException
from app.email.queue import EmailQueue
from app.email.templates import KIND_VERIFICATION_OTP
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.repositories.verification_repository import VerificationRepository
from app.security.otp import hash_otp

from app.events.outbox_publisher import OutboxPublisher
from app.events.auth_events import EmailVerifiedEvent

class VerificationService:
    @staticmethod
    async def create_verification_code(db: AsyncSession, user: User) -> None:
        """
        Generate a cryptographically secure 6-digit OTP, persist only its keyed hash, and queue the email that
        carries it (email_outbox, same transaction). The raw code is never returned, logged or printed.
        """
        code = str(secrets.randbelow(900000) + 100000)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

        await VerificationRepository.create(db, user.id, hash_otp(user.id, code), expires_at)
        await EmailQueue.enqueue(db, KIND_VERIFICATION_OTP, user.email, {"code": code})

    @staticmethod
    async def on_registration(db: AsyncSession, user_id: uuid.UUID) -> None:
        """Issue the verification OTP for a new account, but only when verification is required."""
        if not settings.EMAIL_VERIFICATION_REQUIRED:
            return None
        user = await UserRepository.get_by_id(db, user_id)
        if user is None:
            raise UserNotFoundException(str(user_id))
        await VerificationService.create_verification_code(db, user)

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

        active_code = await VerificationRepository.get_active_code(db, user.id, hash_otp(user.id, code))
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
    async def resend_verification(cls, db: AsyncSession, email: str) -> User | None:
        """
        Invalidate existing codes and queue a new verification email. Returns the user when one was issued, or None
        when the email is unknown or already verified: the caller must respond identically in both cases so the
        endpoint cannot be used to discover which addresses have accounts.
        """
        user = await UserRepository.get_by_email(db, email)
        if not user or user.status == UserStatus.ACTIVE:
            return None

        # Invalidate latest active code if exists
        latest_code = await VerificationRepository.get_latest_active_code(db, user.id)
        if latest_code:
            await VerificationRepository.mark_as_used(db, latest_code.id)

        # Issue new code
        await cls.create_verification_code(db, user)
        return user
