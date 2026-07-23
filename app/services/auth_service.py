import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.auth import LoginRequest
from app.repositories.user_repository import UserRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.services.jwt_service import JWTService
from app.services.refresh_token_service import RefreshTokenService
from app.security.password_hasher import PasswordHasher
from app.utils.device_parser import parse_user_agent
from app.core.exceptions import IncorrectPasswordException, AuthServiceException, InvalidTokenException
from app.core.enums import UserStatus

class AuthService:
    @staticmethod
    async def login(
        db: AsyncSession,
        login_payload: LoginRequest,
        ip_address: str | None,
        user_agent: str | None
    ) -> tuple[str, str, int]:
        """
        Validate user credentials, authenticate, create an active device session, 
        and return the generated JWT access token and plain refresh token.
        """
        # Fetch user
        user = await UserRepository.get_by_email(db, login_payload.email)
        if not user:
            raise IncorrectPasswordException()

        # Check password hash matches
        if not PasswordHasher.verify(user.password_hash, login_payload.password):
            raise IncorrectPasswordException()

        # Enforce account status check
        if user.status != UserStatus.ACTIVE:
            if user.status == UserStatus.PENDING:
                raise AuthServiceException("Email address is not verified yet.")
            raise AuthServiceException("Account is suspended.")

        # Generate access token
        access_token, access_jti, expires_in = JWTService.generate_access_token(user.id, user.email)

        # Generate refresh token
        plain_refresh_token, db_token = await RefreshTokenService.create_refresh_token(db, user.id)

        # Parse client device info
        device, browser, os = parse_user_agent(user_agent)

        # Create active device session
        await SessionRepository.create(
            db=db,
            user_id=user.id,
            refresh_token_id=db_token.id,
            device=device,
            browser=browser,
            os=os,
            ip_address=ip_address,
            expires_at=db_token.expires_at
        )

        # Update last login timestamp
        await UserRepository.update(db, user, {"last_login": datetime.now(timezone.utc)})

        return access_token, plain_refresh_token, expires_in

    @staticmethod
    async def refresh(
        db: AsyncSession,
        raw_refresh_token: str,
        ip_address: str | None,
        user_agent: str | None
    ) -> tuple[str, str, int]:
        """
        Rotates refresh tokens and issues a new access token.
        Checks for security compromises dynamically.
        """
        # Rotate refresh token
        new_plain_token, new_db_token, old_token_id = await RefreshTokenService.rotate_refresh_token(
            db, raw_refresh_token
        )

        # Retrieve current active session linked to rotated token
        session = await SessionRepository.get_by_refresh_token_id(db, old_token_id)
        if not session:
            raise InvalidTokenException("No active session found for the provided token.")

        # Parse user agent details
        device, browser, os = parse_user_agent(user_agent)

        # Update session details dynamically
        session.refresh_token_id = new_db_token.id
        session.last_seen = datetime.now(timezone.utc)
        session.expires_at = new_db_token.expires_at
        session.ip_address = ip_address
        session.device = device
        session.browser = browser
        session.os = os
        
        db.add(session)
        await db.flush()

        # Retrieve user profile
        user = await UserRepository.get_by_id(db, session.user_id)
        if not user or user.status != UserStatus.ACTIVE:
            raise AuthServiceException("User account is inactive.")

        # Issue new Access JWT
        access_token, access_jti, expires_in = JWTService.generate_access_token(user.id, user.email)

        return access_token, new_plain_token, expires_in

    @staticmethod
    async def logout(db: AsyncSession, raw_refresh_token: str) -> None:
        """
        Log out the user session by revoking the refresh token and deleting the device session.
        """
        hashed_token = RefreshTokenService._hash_token(raw_refresh_token)
        db_token = await RefreshTokenRepository.get_by_hash(db, hashed_token)
        
        if db_token:
            # Delete device session
            session = await SessionRepository.get_by_refresh_token_id(db, db_token.id)
            if session:
                await SessionRepository.delete_by_id(db, session.id)
            
            # Revoke token
            await RefreshTokenRepository.revoke_by_id(db, db_token.id)
