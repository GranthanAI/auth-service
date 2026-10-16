"""Refresh-token rotation, replay detection and concurrency, against real Postgres."""

import asyncio

import pytest
from sqlalchemy import select

from app.core.exceptions import CompromiseDetectedException, InvalidTokenException
from app.models.refresh_token import RefreshToken
from app.models.session import Session
from app.services.refresh_token_service import RefreshTokenService

from .conftest import make_expired_token


async def _state(session_factory, user_id):
    """Fresh session => reads only what was actually committed."""
    async with session_factory() as db:
        tokens = (await db.execute(select(RefreshToken).where(RefreshToken.user_id == user_id))).scalars().all()
        sessions = (await db.execute(select(Session).where(Session.user_id == user_id))).scalars().all()
        return tokens, sessions


async def test_rotation_issues_new_token_and_revokes_old(session_factory, user_with_session):
    user_id, old_plain = user_with_session
    async with session_factory() as db:
        new_plain, new_token, _ = await RefreshTokenService.rotate_refresh_token(db, old_plain)
        await db.commit()
    assert new_plain != old_plain
    tokens, _ = await _state(session_factory, user_id)
    by_hash = {t.token_hash: t for t in tokens}
    assert by_hash[RefreshTokenService._hash_token(old_plain)].revoked is True
    assert by_hash[RefreshTokenService._hash_token(new_plain)].revoked is False


async def test_replaying_a_rotated_token_revokes_the_whole_family_durably(session_factory, user_with_session):
    user_id, old_plain = user_with_session
    async with session_factory() as db:
        new_plain, _, _ = await RefreshTokenService.rotate_refresh_token(db, old_plain)
        await db.commit()

    # Attacker (or stale client) replays the already-rotated token.
    async with session_factory() as db:
        with pytest.raises(CompromiseDetectedException):
            await RefreshTokenService.rotate_refresh_token(db, old_plain)
        await db.rollback()  # what the request-scoped get_db does when the endpoint raises

    tokens, sessions = await _state(session_factory, user_id)
    assert all(t.revoked for t in tokens), "the legitimate new token must be revoked too"
    assert sessions == [], "all sessions must be gone"

    # ...so the legitimate holder's newest token is dead as well.
    async with session_factory() as db:
        with pytest.raises(CompromiseDetectedException):
            await RefreshTokenService.rotate_refresh_token(db, new_plain)


async def test_concurrent_refresh_with_same_token_only_one_wins(session_factory, user_with_session):
    user_id, plain = user_with_session

    async def attempt():
        async with session_factory() as db:
            try:
                result = await RefreshTokenService.rotate_refresh_token(db, plain)
                await db.commit()
                return ("ok", result[0])
            except CompromiseDetectedException:
                await db.rollback()
                return ("compromise", None)

    results = await asyncio.gather(*[attempt() for _ in range(6)])
    winners = [r for r in results if r[0] == "ok"]
    assert len(winners) == 1, f"exactly one concurrent refresh may succeed, got {len(winners)}: {results}"

    # The losers are treated as replay: the family is revoked, so no token survives.
    tokens, sessions = await _state(session_factory, user_id)
    assert all(t.revoked for t in tokens)
    assert sessions == []


async def test_expired_token_is_rejected_and_its_session_removal_is_committed(session_factory, user_with_session):
    user_id, _ = user_with_session
    plain = await make_expired_token(session_factory, user_id)
    async with session_factory() as db:
        with pytest.raises(InvalidTokenException):
            await RefreshTokenService.rotate_refresh_token(db, plain)
        await db.rollback()
    _, sessions = await _state(session_factory, user_id)
    # one session belonged to the expired token and must be gone; the live one is untouched
    assert len(sessions) == 1


async def test_unknown_token_is_rejected(session_factory):
    async with session_factory() as db:
        with pytest.raises(InvalidTokenException):
            await RefreshTokenService.rotate_refresh_token(db, "not-a-real-token")
