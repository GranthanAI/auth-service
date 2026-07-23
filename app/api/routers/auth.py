from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.schemas.user import UserResponse, UserCreate
from app.services.user_service import UserService
from app.core.exceptions import UserAlreadyExistsException, AuthServiceException

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_create: UserCreate,
    db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """
    Register a new user account. Verify that the email is unique, hash the password, 
    and persist the identity record.
    """
    try:
        user = await UserService.register_user(db, user_create)
        return user  # type: ignore
    except UserAlreadyExistsException as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except AuthServiceException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
