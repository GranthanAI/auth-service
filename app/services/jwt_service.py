import uuid
from app.security.jwt_manager import JWTManager
from app.core.config import settings

class JWTService:
    @staticmethod
    def generate_access_token(user_id: uuid.UUID, email: str) -> tuple[str, str, int]:
        """
        Generate a signed JWT access token for a user.
        Returns a tuple of: (access_token_string, jti_string, expires_in_seconds)
        """
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        token, jti = JWTManager.encode_access_token(user_id, email, expires_in)
        return token, jti, expires_in
