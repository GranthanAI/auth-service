from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Cookie
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.schemas.user import UserResponse, UserCreate
from app.api.schemas.auth import LoginRequest, TokenResponse
from app.services.user_service import UserService
from app.services.auth_service import AuthService
from app.core.exceptions import (
    UserAlreadyExistsException,
    AuthServiceException,
    IncorrectPasswordException,
    InvalidTokenException,
    CompromiseDetectedException
)

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_create: UserCreate,
    db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """
    Onboard a new user profile using basic validations and encrypt credentials.
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

@router.post("/login", response_model=TokenResponse)
async def login(
    response: Response,
    request: Request,
    login_payload: LoginRequest,
    db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """
    Log in a user. Verifies email/password credentials, logs the device session, 
    and sets a secure HttpOnly refresh token cookie.
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        access_token, refresh_token, expires_in = await AuthService.login(
            db, login_payload, ip_address, user_agent
        )
        
        # Set refresh token cookie securely
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,
            samesite="strict",
            path="/",  # Accessible to /auth/logout and /auth/refresh
            max_age=30 * 24 * 60 * 60  # 30 days
        )
        return TokenResponse(access_token=access_token, expires_in=expires_in)
    except IncorrectPasswordException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password."
        )
    except AuthServiceException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    response: Response,
    request: Request,
    refresh_token: str | None = Cookie(None),
    db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """
    Rotate refresh tokens and issue a new access token (Refresh Token Rotation).
    If token reuse is detected, all user sessions are terminated for safety.
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token cookie."
        )
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        access_token, new_refresh_token, expires_in = await AuthService.refresh(
            db, refresh_token, ip_address, user_agent
        )
        
        # Set updated refresh token cookie
        response.set_cookie(
            key="refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=True,
            samesite="strict",
            path="/",
            max_age=30 * 24 * 60 * 60
        )
        return TokenResponse(access_token=access_token, expires_in=expires_in)
    except InvalidTokenException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except CompromiseDetectedException as e:
        # Clear token cookie to prevent infinite error loops
        response.delete_cookie(key="refresh_token", path="/")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except AuthServiceException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/logout")
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(None),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Revoke current refresh token and clear client cookies.
    """
    if refresh_token:
        try:
            await AuthService.logout(db, refresh_token)
        except Exception:
            pass
    # Clean cookie
    response.delete_cookie(key="refresh_token", path="/")
    return {"message": "Logged out successfully."}
