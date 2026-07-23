from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.api.deps import get_db, get_current_user
from app.api.schemas.user import UserResponse, ProfileUpdate
from app.services.user_service import UserService
from app.core.exceptions import AuthServiceException, UserNotFoundException

router = APIRouter(prefix="/auth", tags=["users"])

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    """
    Get profile information of the currently authenticated user.
    """
    return current_user

@router.patch("/profile", response_model=UserResponse)
async def update_profile(
    profile_update: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Update profile fields (full name, avatar URL) of the currently authenticated user.
    """
    try:
        updated_user = await UserService.update_profile(db, current_user.id, profile_update)
        return updated_user
    except UserNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except AuthServiceException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
