import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.api.schemas.user import UserCreate

class UserRepository:
    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> User | None:
        result = await db.execute(select(User).where(func.lower(User.email) == email.lower()))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, user_create: UserCreate, hashed_password: str) -> User:
        db_user = User(
            email=user_create.email.lower(),
            password_hash=hashed_password,
            full_name=user_create.full_name,
        )
        db.add(db_user)
        await db.flush()
        return db_user

    @staticmethod
    async def update(db: AsyncSession, user_obj: User, updates: dict) -> User:
        for field, value in updates.items():
            if hasattr(user_obj, field):
                setattr(user_obj, field, value)
        db.add(user_obj)
        await db.flush()
        return user_obj
