import uuid
from datetime import datetime
from pydantic import BaseModel

class SessionResponse(BaseModel):
    id: uuid.UUID
    device: str | None
    browser: str | None
    os: str | None
    ip_address: str | None
    created_at: datetime
    last_seen: datetime
    expires_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
