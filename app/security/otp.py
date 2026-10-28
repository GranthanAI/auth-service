import hashlib
import hmac
import uuid

from app.core.config import settings


def hash_otp(user_id: uuid.UUID, code: str) -> str:
    """Keyed hash of a verification OTP, bound to the user. A bare SHA-256 would fall to a 10^6 brute force if the
    table leaked; the server-side key (OTP_HMAC_KEY, defaulting to JWT_SECRET_KEY) prevents that."""
    key = (settings.OTP_HMAC_KEY or settings.JWT_SECRET_KEY).encode("utf-8")
    return hmac.new(key, f"{user_id}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()
