"""Regression: POST /auth/register must return 201 with a complete user body (it failed
with 500 / MissingGreenlet when email verification is optional)."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db, get_redis
from app.core.config import settings
from app.main import app


@pytest.mark.parametrize("verification_required", [False, True])
async def test_register_returns_the_created_user(session_factory, monkeypatch, verification_required):
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_REQUIRED", verification_required)

    async def _db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = f"reg_{uuid.uuid4().hex[:10]}@example.com"
            r = await client.post("/auth/register", json={"email": email, "password": "SecurePassword123!", "full_name": "Reg Test"})
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == email and body["updated_at"] and body["created_at"]
    assert body["status"] == ("PENDING" if verification_required else "ACTIVE")
