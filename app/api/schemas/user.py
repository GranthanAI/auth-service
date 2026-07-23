import uuid
from datetime import datetime
import re
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict

from app.core.enums import UserStatus

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=128)
    full_name: str | None = Field(None, min_length=2, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character.")
        return v

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
