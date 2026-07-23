from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass

# Import models here to make sure they are registered on Base.metadata
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.models.session import Session
