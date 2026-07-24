from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.models.user import User
from app.api.deps import get_db, get_current_user, get_redis
from app.api.schemas.user import UserResponse, ProfileUpdate, PasswordChangeRequest
from app.services.user_service import UserService
from app.services.password_service import PasswordService
from app.services.audit_service import AuditService
from app.cache.jwt_blacklist import JWTBlacklist
from app.core.exceptions import (
    AuthServiceException,
    UserNotFoundException,
    IncorrectPasswordException,
    SamePasswordException
)

router = APIRouter(prefix="/auth", tags=["users"])

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    """
    Get profile information of the currently authenticated user.
    """
    return current_user

@router.patch("/profile", response_model=UserResponse)
async def update_profile(
    request: Request,
    profile_update: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Update profile fields (full name, avatar URL) of the currently authenticated user.
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        updated_user = await UserService.update_profile(db, current_user.id, profile_update)
        
        # Log Audit Log
        await AuditService.log_action(
            db=db,
            user_id=current_user.id,
            action="PROFILE_UPDATED",
            ip_address=ip_address,
            user_agent=user_agent
        )
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

@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    request: Request,
    payload: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis | None = Depends(get_redis)
) -> dict:
    """
    Change the password of the currently authenticated user.
    Checks correctness of the old password, validates complexity, and prevents recycling.
    Blacklists the active access token to force re-authentication or invalidate the token.
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        await PasswordService.change_password(
            db=db,
            user_id=current_user.id,
            old_password=payload.old_password,
            new_password=payload.new_password
        )
        
        # Blacklist the current active access token (since credentials changed)
        jti = getattr(request.state, "jti", None)
        token_exp = getattr(request.state, "token_exp", None)
        if jti and token_exp:
            from datetime import datetime, timezone
            now = int(datetime.now(timezone.utc).timestamp())
            remaining = token_exp - now
            if remaining > 0:
                await JWTBlacklist.blacklist_token(jti, remaining, redis=redis)

        # Log Audit Log
        await AuditService.log_action(
            db=db,
            user_id=current_user.id,
            action="PASSWORD_CHANGED",
            ip_address=ip_address,
            user_agent=user_agent
        )
        return {"message": "Password changed successfully."}
    except (IncorrectPasswordException, SamePasswordException) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
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
