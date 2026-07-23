import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.user_service import UserService
from app.repositories.user_repository import UserRepository
from app.security.password_hasher import PasswordHasher
from app.security.validators import validate_password_strength
from app.core.exceptions import IncorrectPasswordException, SamePasswordException

class PasswordService:
    @staticmethod
    async def change_password(
        db: AsyncSession,
        user_id: uuid.UUID,
        old_password: str,
        new_password: str
    ) -> None:
        """
        Change the user's password.
        Validates the current password, checks complexity constraints for the new password,
        and prevents reusing the same password.
        """
        # Fetch the user
        user = await UserService.get_user_by_id(db, user_id)

        # Verify old password
        if not PasswordHasher.verify(user.password_hash, old_password):
            raise IncorrectPasswordException()

        # Verify new password is not identical to the old password
        if old_password == new_password:
            raise SamePasswordException()
            
        if PasswordHasher.verify(user.password_hash, new_password):
            raise SamePasswordException()

        # Validate complexity constraints
        validate_password_strength(new_password)

        # Hash the new password and persist changes
        new_password_hash = PasswordHasher.hash(new_password)
        await UserRepository.update(db, user, {"password_hash": new_password_hash})
