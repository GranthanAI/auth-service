"""EMAIL_VERIFICATION_REQUIRED toggles sign-up/login between direct and OTP-gated (real Postgres)."""
import pytest
from sqlalchemy import select

from app.api.schemas.auth import LoginRequest
from app.api.schemas.user import UserCreate
from app.core.config import settings
from app.core.enums import UserStatus
from app.core.exceptions import AuthServiceException
from app.models.email_verification import EmailVerification
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.services.verification_service import VerificationService

PASSWORD = "Str0ng-Passw0rd!x"


async def _register(db, email):
    user = await UserService.register_user(db, UserCreate(email=email, password=PASSWORD, full_name="Test User"))
    await VerificationService.on_registration(db, user.id)
    await db.commit()
    return user


async def _codes(db, user_id):
    return (await db.execute(select(EmailVerification).where(EmailVerification.user_id == user_id))).scalars().all()


async def _login(db, email):
    return await AuthService.login(db, LoginRequest(email=email, password=PASSWORD), "127.0.0.1", "pytest")


@pytest.mark.asyncio
async def test_flag_off_signup_is_active_and_login_works(session_factory, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_REQUIRED", False)
    async with session_factory() as db:
        user = await _register(db, "direct@example.com")
        assert user.status == UserStatus.ACTIVE
        assert await _codes(db, user.id) == []
        access, refresh, _ = await _login(db, "direct@example.com")
        assert access and refresh


@pytest.mark.asyncio
async def test_flag_on_signup_pending_with_code_and_login_rejected(session_factory, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_REQUIRED", True)
    async with session_factory() as db:
        user = await _register(db, "gated@example.com")
        assert user.status == UserStatus.PENDING
        assert len(await _codes(db, user.id)) == 1
        with pytest.raises(AuthServiceException, match="not verified"):
            await _login(db, "gated@example.com")


@pytest.mark.asyncio
async def test_turning_flag_off_lets_pending_user_login(session_factory, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_REQUIRED", True)
    async with session_factory() as db:
        await _register(db, "later@example.com")
        monkeypatch.setattr(settings, "EMAIL_VERIFICATION_REQUIRED", False)
        access, _, _ = await _login(db, "later@example.com")
        assert access
