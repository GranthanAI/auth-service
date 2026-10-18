"""Device sessions (is_current, revoke-others used by password change) against real
PostgreSQL, and avatar URL validation."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.api.schemas.user import ProfileUpdate
from app.core.enums import UserStatus
from app.models.refresh_token import RefreshToken
from app.models.session import Session
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.services.refresh_token_service import RefreshTokenService
from app.services.session_service import SessionService


async def _user_with_sessions(session_factory, n: int):
    """A user with `n` device sessions. Returns (user_id, [plain refresh tokens])."""
    async with session_factory() as db:
        user = User(id=uuid.uuid4(), email=f"{uuid.uuid4().hex[:8]}@example.com", password_hash="x",
                    is_email_verified=True, status=UserStatus.ACTIVE)
        db.add(user)
        await db.flush()
        tokens = []
        for i in range(n):
            plain, token = await RefreshTokenService.create_refresh_token(db, user.id)
            await SessionRepository.create(db, user.id, token.id, f"Device {i}", "Browser", "OS", "127.0.0.1",
                                           datetime.now(timezone.utc) + timedelta(days=30))
            tokens.append(plain)
        await db.commit()
        return user.id, tokens


async def _state(session_factory, user_id):
    async with session_factory() as db:
        sessions = (await db.execute(select(Session).where(Session.user_id == user_id))).scalars().all()
        tokens = (await db.execute(select(RefreshToken).where(RefreshToken.user_id == user_id))).scalars().all()
        return sessions, tokens


async def test_current_session_is_identified_from_the_refresh_cookie(session_factory):
    user_id, tokens = await _user_with_sessions(session_factory, 2)
    async with session_factory() as db:
        current = await SessionService.current_session(db, user_id, tokens[1])
        assert current is not None and current.device == "Device 1"
        assert await SessionService.current_session(db, user_id, None) is None
        assert await SessionService.current_session(db, user_id, "not-a-token") is None


async def test_someone_elses_cookie_is_not_my_session(session_factory):
    alice, _ = await _user_with_sessions(session_factory, 1)
    _, bob_tokens = await _user_with_sessions(session_factory, 1)
    async with session_factory() as db:
        assert await SessionService.current_session(db, alice, bob_tokens[0]) is None


async def test_revoke_other_sessions_keeps_only_the_callers(session_factory):
    user_id, tokens = await _user_with_sessions(session_factory, 3)
    async with session_factory() as db:
        assert await SessionService.revoke_other_sessions(db, user_id, tokens[0]) == 2
        await db.commit()
    sessions, refresh = await _state(session_factory, user_id)
    assert [s.device for s in sessions] == ["Device 0"]
    live = [t for t in refresh if not t.revoked]
    assert len(live) == 1 and live[0].token_hash == RefreshTokenService._hash_token(tokens[0])
    # the revoked devices can no longer refresh (replay of a revoked token = compromise)
    async with session_factory() as db:
        with pytest.raises(Exception):
            await RefreshTokenService.rotate_refresh_token(db, tokens[1])


async def test_without_a_valid_cookie_every_session_is_revoked(session_factory):
    user_id, _ = await _user_with_sessions(session_factory, 2)
    async with session_factory() as db:
        await SessionService.revoke_other_sessions(db, user_id, None)
        await db.commit()
    sessions, refresh = await _state(session_factory, user_id)
    assert sessions == [] and all(t.revoked for t in refresh)


@pytest.mark.parametrize("url", ["https://cdn.example.com/a.png", ""])
def test_avatar_accepts_https_or_empty(url):
    assert ProfileUpdate(avatar_url=url).avatar_url == url


@pytest.mark.parametrize("url", ["http://example.com/a.png", "javascript:alert(1)", "data:image/png;base64,AAA",
                                 "file:///etc/passwd", "https://", "https://ex ample.com/a.png", "ftp://x/y"])
def test_avatar_rejects_other_schemes(url):
    with pytest.raises(ValidationError):
        ProfileUpdate(avatar_url=url)


async def test_signed_out_device_refreshing_does_not_end_the_remaining_session(session_factory):
    """Regression: an intentionally signed-out device that tries to refresh must get a plain
    'invalid token' for itself only. Before, its token was marked revoked, the attempt looked
    like token theft, and every session (including the one that signed it out) was ended."""
    from app.core.exceptions import CompromiseDetectedException, InvalidTokenException

    user_id, tokens = await _user_with_sessions(session_factory, 2)
    async with session_factory() as db:
        await SessionService.revoke_other_sessions(db, user_id, tokens[0])
        await db.commit()
    async with session_factory() as db:
        with pytest.raises(InvalidTokenException) as exc:
            await RefreshTokenService.rotate_refresh_token(db, tokens[1])
        assert not isinstance(exc.value, CompromiseDetectedException)
        await db.rollback()
    async with session_factory() as db:  # the kept device still works
        new_plain, _, _ = await RefreshTokenService.rotate_refresh_token(db, tokens[0])
        await db.commit()
    assert new_plain


async def test_login_activates_a_pending_account_when_verification_is_not_required(session_factory, monkeypatch):
    """Regression: a PENDING account could log in (200) but every authenticated call then returned 401
    ('inactive or suspended'), so the UI showed 'Your session expired' right after sign-in."""
    from app.api.schemas.auth import LoginRequest
    from app.core.config import settings
    from app.security.password_hasher import PasswordHasher
    from app.services.auth_service import AuthService

    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_REQUIRED", False)
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    async with session_factory() as db:
        user = User(id=uuid.uuid4(), email=email, password_hash=PasswordHasher.hash("Str0ng#Passw0rd!"),
                    is_email_verified=False, status=UserStatus.PENDING)
        db.add(user)
        await db.commit()
    async with session_factory() as db:
        await AuthService.login(db, LoginRequest(email=email, password="Str0ng#Passw0rd!"), "127.0.0.1", "pytest")
        await db.commit()
    async with session_factory() as db:
        row = (await db.execute(select(User).where(User.email == email))).scalar_one()
        assert row.status == UserStatus.ACTIVE and row.is_email_verified is False
