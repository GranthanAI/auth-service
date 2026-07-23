import uuid
from datetime import datetime, timezone
import jwt
from jwt.exceptions import PyJWTError

from app.core.config import settings

class JWTManager:
    @staticmethod
    def encode_access_token(user_id: uuid.UUID, email: str, expires_in_seconds: int) -> tuple[str, str]:
        """
        Generate a signed JWT access token.
        Returns a tuple of (token_string, jti_string).
        """
        now = datetime.now(timezone.utc)
        jti = str(uuid.uuid4())
        payload = {
            "iss": "https://auth.granthan.com",
            "sub": str(user_id),
            "email": email,
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int(now.timestamp() + expires_in_seconds)
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        return token, jti

    @staticmethod
    def decode_access_token(token: str) -> dict | None:
        """
        Decode and verify a signed JWT access token.
        Returns claims payload or None if invalid/expired.
        """
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
                options={"require": ["sub", "email", "jti", "exp", "iat"]}
            )
            return payload
        except PyJWTError:
            return None
