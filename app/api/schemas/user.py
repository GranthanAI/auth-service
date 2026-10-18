import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict

from app.core.enums import UserStatus
from app.security.validators import validate_password_strength

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=128)
    full_name: str | None = Field(None, min_length=2, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password_strength_rule(cls, v: str) -> str:
        return validate_password_strength(v)

class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    avatar_url: str | None
    is_email_verified: bool
    status: UserStatus
    created_at: datetime
    updated_at: datetime
    last_login: datetime | None

    model_config = ConfigDict(from_attributes=True)

class ProfileUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=100)
    avatar_url: str | None = Field(None, max_length=1024)

    @field_validator("avatar_url")
    @classmethod
    def validate_avatar_url(cls, v: str | None) -> str | None:
        """An https image URL, or "" to remove the avatar. Other schemes (http:, data:,
        javascript:, file:) are rejected."""
        if v is None:
            return v
        v = v.strip()
        if v == "":
            return v
        from urllib.parse import urlparse

        parsed = urlparse(v)
        if parsed.scheme != "https" or not parsed.netloc or any(c.isspace() for c in v):
            raise ValueError("Avatar must be an https:// URL.")
        return v

class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength_rule(cls, v: str) -> str:
        return validate_password_strength(v)
