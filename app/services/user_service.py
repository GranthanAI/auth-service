import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_repository import UserRepository
from app.api.schemas.user import UserCreate, ProfileUpdate
from app.core.config import settings
from app.core.enums import UserStatus
from app.models.user import User
from app.security.password_hasher import PasswordHasher
from app.core.exceptions import UserAlreadyExistsException, UserNotFoundException

from app.events.outbox_publisher import OutboxPublisher
from app.events.auth_events import UserRegisteredEvent

class UserService:
    @staticmethod
    async def register_user(db: AsyncSession, user_create: UserCreate) -> User:
        """Register a new user after verifying that the email is unique and hashing the password."""
        existing_user = await UserRepository.get_by_email(db, user_create.email)
        if existing_user:
            raise UserAlreadyExistsException(user_create.email)

        # Hash the plain text password
        hashed_password = PasswordHasher.hash(user_create.password)

        # Persist the user
        user = await UserRepository.create(db, user_create, hashed_password)

        if not settings.EMAIL_VERIFICATION_REQUIRED and user.status == UserStatus.PENDING:
            # No verification step: the account is usable right away. is_email_verified stays False
            # because the address genuinely has not been verified.
            user.status = UserStatus.ACTIVE
            db.add(user)
            await db.flush()

        # Transactionally queue UserRegistered outbox event
        event = UserRegisteredEvent(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name
        )
        await OutboxPublisher.queue_event(db, "UserRegistered", event.model_dump(mode="json"))

        # Load server-generated columns (e.g. updated_at, expired by the status UPDATE above)
        # inside the async session; otherwise serialising the response lazy-loads them
        # outside the greenlet and registration fails with a 500 (MissingGreenlet).
        await db.refresh(user)
        return user

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
        """Retrieve a user by ID, raising an exception if not found."""
        user = await UserRepository.get_by_id(db, user_id)
        if not user:
            raise UserNotFoundException(str(user_id))
        return user

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> User:
        """Retrieve a user by email, raising an exception if not found."""
        user = await UserRepository.get_by_email(db, email)
        if not user:
            raise UserNotFoundException(email)
        return user

    @staticmethod
    async def update_profile(db: AsyncSession, user_id: uuid.UUID, profile_update: ProfileUpdate) -> User:
        """Update a user's profile fields dynamically based on specified inputs."""
        user = await UserService.get_user_by_id(db, user_id)
        updates = profile_update.model_dump(exclude_unset=True)
        return await UserRepository.update(db, user, updates)
