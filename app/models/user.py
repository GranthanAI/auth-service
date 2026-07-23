import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Enum as SQLEnum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.enums import UserStatus

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    full_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True
    )
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        SQLEnum(UserStatus, name="userstatus_enum"),
        default=UserStatus.PENDING,
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
