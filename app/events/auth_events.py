import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, EmailStr, Field

class BaseEvent(BaseModel):
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserRegisteredEvent(BaseEvent):
    user_id: uuid.UUID
    email: EmailStr
    full_name: str | None

class EmailVerifiedEvent(BaseEvent):
    user_id: uuid.UUID
    email: EmailStr

class PasswordResetEvent(BaseEvent):
    user_id: uuid.UUID
    email: EmailStr
