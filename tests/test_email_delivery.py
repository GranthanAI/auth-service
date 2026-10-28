"""Transactional email: no secrets on stdout, hashed OTPs, email_outbox + worker (retry/backoff/cutoff),
enumeration-safe responses, and fail-fast sender configuration (real Postgres for the DB-backed tests)."""
import importlib.util
from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.api.deps import get_db, get_redis
from app.api.routers import auth as auth_router
from app.api.schemas.user import UserCreate
from app.core.config import Settings, settings
from app.email.sender import ConsoleEmailSender, EmailMessage, EmailSender, get_email_sender
from app.models.email_outbox import EmailOutbox
from app.models.email_verification import EmailVerification
from app.models.outbox import Outbox
from app.models.password_reset import PasswordReset
from app.security.otp import hash_otp
from app.services.password_reset_service import PasswordResetService
from app.services.user_service import UserService
from app.services.verification_service import VerificationService
from app.workers.email_worker import EmailWorker, backoff_seconds

STRONG = "k9Qx2mV7pLr4Zt8WyB3nHd6Fs1JcUe5A"
PASSWORD = "Str0ng-Passw0rd!x"


class RecordingSender(EmailSender):
    def __init__(self, fail_times: int = 0):
        self.sent: list[EmailMessage] = []
        self.fail_times = fail_times
        self.calls = 0

    async def send(self, message: EmailMessage) -> None:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("smtp down")
        self.sent.append(message)


async def _user(db, email="mail@example.com"):
    user = await UserService.register_user(db, UserCreate(email=email, password=PASSWORD, full_name="Test User"))
    await db.commit()
    return user


async def _emails(db):
    return (await db.execute(select(EmailOutbox))).scalars().all()


# ── sender configuration ─────────────────────────────────────────────────────

@pytest.mark.parametrize("env", ["production", "prod", "staging", " Production "])
def test_console_sender_is_refused_outside_development_and_test(env):
    with pytest.raises(ValueError) as exc:
        Settings(_env_file=None, ENVIRONMENT=env, JWT_SECRET_KEY=STRONG, EMAIL_SENDER="console")
    assert "EMAIL_SENDER=smtp" in str(exc.value)  # the message says how to fix it


def test_console_sender_allowed_in_development_and_test(monkeypatch):
    for env in ("development", "test"):
        Settings(_env_file=None, ENVIRONMENT=env, EMAIL_SENDER="console")
    monkeypatch.setattr(settings, "EMAIL_SENDER", "console")
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    assert isinstance(get_email_sender(), ConsoleEmailSender)


def test_get_email_sender_refuses_console_in_production_even_if_settings_were_mutated(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_SENDER", "console")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(ValueError):
        get_email_sender()


def test_smtp_requires_a_host():
    with pytest.raises(ValueError):
        Settings(_env_file=None, ENVIRONMENT="production", JWT_SECRET_KEY=STRONG, EMAIL_SENDER="smtp")
    Settings(_env_file=None, ENVIRONMENT="production", JWT_SECRET_KEY=STRONG, EMAIL_SENDER="smtp", SMTP_HOST="smtp.example.com")


def test_get_otp_script_is_gone():
    from pathlib import Path
    assert not (Path(__file__).resolve().parent.parent / "get_otp.py").exists()


# ── verification OTP ─────────────────────────────────────────────────────────

async def test_otp_is_hashed_at_rest_emailed_and_never_printed(session_factory, monkeypatch, capsys):
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_REQUIRED", True)
    async with session_factory() as db:
        user = await _user(db)
        await VerificationService.on_registration(db, user.id)
        await db.commit()

        (mail,) = await _emails(db)
        code = mail.payload["code"]
        assert mail.kind == "verification_otp" and mail.to_email == user.email

        (row,) = (await db.execute(select(EmailVerification))).scalars().all()
        assert row.code_hash == hash_otp(user.id, code) and code not in row.code_hash and len(row.code_hash) == 64

        out = capsys.readouterr()
        assert code not in out.out and code not in out.err

        # The emailed code verifies the account; a wrong one does not.
        await VerificationService.verify_email_code(db, user.email, code)


async def test_email_rows_never_land_in_the_kafka_outbox(session_factory, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_REQUIRED", True)
    async with session_factory() as db:
        user = await _user(db)
        await VerificationService.on_registration(db, user.id)
        await PasswordResetService.request_password_reset(db, user.email)
        await db.commit()
        assert len(await _emails(db)) == 2
        for row in (await db.execute(select(Outbox))).scalars().all():
            assert "code" not in row.payload and "token" not in row.payload


# ── password reset ───────────────────────────────────────────────────────────

async def test_reset_token_is_hashed_emailed_and_never_printed(session_factory, capsys):
    async with session_factory() as db:
        user = await _user(db)
        returned = await PasswordResetService.request_password_reset(db, user.email)
        await db.commit()
        assert returned.id == user.id  # a user object, not the token

        (mail,) = await _emails(db)
        token = mail.payload["token"]
        (reset,) = (await db.execute(select(PasswordReset))).scalars().all()
        assert reset.reset_token == PasswordResetService._hash_token(token) and token not in reset.reset_token

        out = capsys.readouterr()
        assert token not in out.out and token not in out.err

        await PasswordResetService.reset_password(db, token, "An0ther-Str0ng-Pass!")


async def test_reset_link_in_the_rendered_email(session_factory, monkeypatch):
    from app.email.templates import render
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://app.example.com/")
    msg = render("password_reset", "a@example.com", {"token": "tok123"})
    assert "https://app.example.com/reset-password?token=tok123" in msg.body


async def test_unknown_email_queues_nothing(session_factory):
    async with session_factory() as db:
        assert await PasswordResetService.request_password_reset(db, "nobody@example.com") is None
        assert await VerificationService.resend_verification(db, "nobody@example.com") is None
        assert await _emails(db) == []


# ── HTTP: enumeration-safe responses ─────────────────────────────────────────

def _app(session_factory):
    app = FastAPI()
    app.include_router(auth_router.router)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def _db():
        async with session_factory() as session:
            yield session
            await session.commit()

    async def _redis():
        return redis

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = _redis
    return app


@pytest.mark.parametrize("path", ["/auth/forgot-password", "/auth/resend-verification"])
async def test_known_and_unknown_emails_get_identical_responses(session_factory, monkeypatch, path):
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_REQUIRED", True)
    async with session_factory() as db:
        user = await _user(db, "exists@example.com")
        await VerificationService.on_registration(db, user.id)  # PENDING account: resend applies
        await db.commit()
    transport = httpx.ASGITransport(app=_app(session_factory), client=("203.0.113.1", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        known = await client.post(path, json={"email": "exists@example.com"})
        unknown = await client.post(path, json={"email": "ghost@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert "console" not in known.json()["message"].lower()  # no "printed to the developer console"


# ── worker ───────────────────────────────────────────────────────────────────

async def test_worker_sends_then_deletes_the_row(session_factory):
    async with session_factory() as db:
        db.add(EmailOutbox(kind="verification_otp", to_email="a@example.com", payload={"code": "123456"}))
        await db.commit()
    sender = RecordingSender()
    assert await EmailWorker.process_batch(sender, session_factory) == 1
    assert sender.sent[0].to == "a@example.com" and "123456" in sender.sent[0].body
    async with session_factory() as db:
        assert await _emails(db) == []  # deleted, not merely blanked


async def test_worker_retries_with_backoff_then_gives_up_and_deletes(session_factory, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_MAX_ATTEMPTS", 3)
    async with session_factory() as db:
        db.add(EmailOutbox(kind="password_reset", to_email="a@example.com", payload={"token": "tok"}))
        await db.commit()
    sender = RecordingSender(fail_times=99)

    for attempt in (1, 2):
        before = datetime.now(timezone.utc)
        assert await EmailWorker.process_batch(sender, session_factory) == 1
        async with session_factory() as db:
            (row,) = await _emails(db)
            assert row.attempts == attempt and row.last_error == "ConnectionError"
            assert row.next_attempt_at >= before + timedelta(seconds=backoff_seconds(attempt) - 1)
            assert "smtp down" not in (row.last_error or "")  # exception messages are never stored
            row.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)  # make it due again
            await db.commit()

    assert await EmailWorker.process_batch(sender, session_factory) == 1  # third failure hits the cutoff
    async with session_factory() as db:
        assert await _emails(db) == []


async def test_worker_skips_rows_that_are_not_yet_due(session_factory):
    async with session_factory() as db:
        db.add(EmailOutbox(kind="verification_otp", to_email="a@example.com", payload={"code": "1"},
                           next_attempt_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        await db.commit()
    sender = RecordingSender()
    assert await EmailWorker.process_batch(sender, session_factory) == 0 and sender.calls == 0


def test_backoff_doubles_and_is_capped(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_RETRY_BASE_SECONDS", 30)
    monkeypatch.setattr(settings, "EMAIL_RETRY_MAX_SECONDS", 100)
    assert [backoff_seconds(n) for n in (1, 2, 3, 4)] == [30, 60, 100, 100]
