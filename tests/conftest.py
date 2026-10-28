"""Test fixtures: a real PostgreSQL database (not mocks), because the properties
under test - atomic refresh-token rotation, commits surviving a failed request -
only exist in a real database.

Uses a dedicated database (default auth_test_db on the shared dev Postgres; the
container publishes 5433 as well as 5432). Override with AUTH_TEST_DATABASE_URL.
Tables are created fresh for every test and dropped afterwards; the application's
own auth_db is never touched.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models.email_verification  # noqa: F401  (register every table on Base.metadata)
import app.models.audit_log  # noqa: F401
import app.models.outbox  # noqa: F401
import app.models.email_outbox  # noqa: F401
import app.models.password_reset  # noqa: F401
import app.models.refresh_token  # noqa: F401
import app.models.session  # noqa: F401
import app.models.user  # noqa: F401
from app.core.enums import UserStatus
from app.db.base import Base
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.session_repository import SessionRepository
from app.security.token_generator import TokenGenerator
from app.services.refresh_token_service import RefreshTokenService

TEST_DB_URL = os.getenv(
    "AUTH_TEST_DATABASE_URL", "postgresql+asyncpg://postgres:1234@127.0.0.1:5433/auth_test_db"
)


async def _ensure_database() -> None:
    url = make_url(TEST_DB_URL)
    conn = await asyncpg.connect(
        user=url.username, password=url.password, host=url.host, port=url.port, database="postgres"
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def session_factory():
    try:
        await _ensure_database()
    except OSError as exc:  # Postgres not reachable: say so instead of silently passing
        pytest.skip(f"PostgreSQL not reachable for auth tests: {exc}")
    engine = create_async_engine(TEST_DB_URL, pool_size=5)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def user_with_session(session_factory):
    """A verified user with one live refresh token and its session.
    Returns (user_id, plain_refresh_token)."""
    async with session_factory() as db:
        user = User(
            id=uuid.uuid4(),
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
            is_email_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()
        plain, token = await RefreshTokenService.create_refresh_token(db, user.id)
        await SessionRepository.create(
            db, user.id, token.id, "Desktop", "Chrome", "Windows", "127.0.0.1",
            datetime.now(timezone.utc) + timedelta(days=30),
        )
        await db.commit()
        return user.id, plain


async def make_expired_token(session_factory, user_id):
    """An already-expired refresh token (with a session) for the expiry path."""
    async with session_factory() as db:
        plain = TokenGenerator.generate_secure_token()
        token = await RefreshTokenRepository.create(
            db, user_id, RefreshTokenService._hash_token(plain), datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        await SessionRepository.create(
            db, user_id, token.id, None, None, None, None, datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        await db.commit()
        return plain
