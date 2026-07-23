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

class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength_rule(cls, v: str) -> str:
        return validate_password_strength(v)
