from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Cookie
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.schemas.user import UserResponse, UserCreate
from app.api.schemas.auth import (
    LoginRequest,
    TokenResponse,
    EmailVerifyRequest,
    ResendVerifyRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest
)
from app.services.user_service import UserService
from app.services.auth_service import AuthService
from app.services.verification_service import VerificationService
from app.services.password_reset_service import PasswordResetService
from app.services.audit_service import AuditService
from app.repositories.user_repository import UserRepository
from app.core.exceptions import (
    UserAlreadyExistsException,
    AuthServiceException,
    IncorrectPasswordException,
    InvalidTokenException,
    CompromiseDetectedException,
    UserNotFoundException,
    SamePasswordException
)

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    user_create: UserCreate,
    db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """
    Onboard a new user profile using basic validations and encrypt credentials.
    Generates a verification OTP automatically.
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        user = await UserService.register_user(db, user_create)
        
        # Trigger verification code creation automatically
        await VerificationService.create_verification_code(db, user.id)
        
        # Log Audit Log
        await AuditService.log_action(
            db=db,
            user_id=user.id,
            action="USER_REGISTERED",
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_dict={"email": user.email}
        )
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
        
        # Fetch user to log
        user = await UserRepository.get_by_email(db, login_payload.email)
        user_id = user.id if user else None
        
        # Log Audit Log
        await AuditService.log_action(
            db=db,
            user_id=user_id,
            action="USER_LOGGED_IN",
            ip_address=ip_address,
            user_agent=user_agent
        )

        # Set refresh token cookie securely
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,
            samesite="strict",
            path="/",
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
    request: Request,
    refresh_token: str | None = Cookie(None),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Revoke current refresh token and clear client cookies.
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    if refresh_token:
        try:
            # Look up token to find user_id for logging logout
            from app.services.refresh_token_service import RefreshTokenService
            from app.repositories.refresh_token_repository import RefreshTokenRepository
            hashed_token = RefreshTokenService._hash_token(refresh_token)
            db_token = await RefreshTokenRepository.get_by_hash(db, hashed_token)
            user_id = db_token.user_id if db_token else None
            
            await AuthService.logout(db, refresh_token)
            
            if user_id:
                await AuditService.log_action(
                    db=db,
                    user_id=user_id,
                    action="USER_LOGGED_OUT",
                    ip_address=ip_address,
                    user_agent=user_agent
                )
        except Exception:
            pass
    # Clean cookie
    response.delete_cookie(key="refresh_token", path="/")
    return {"message": "Logged out successfully."}

@router.post("/verify-email")
async def verify_email(
    request: Request,
    payload: EmailVerifyRequest,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Verify the user's email address using the generated OTP code.
    Changes user status to ACTIVE on successful validation.
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        await VerificationService.verify_email_code(db, payload.email, payload.code)
        
        # Log Audit Log
        user = await UserService.get_user_by_email(db, payload.email)
        await AuditService.log_action(
            db=db,
            user_id=user.id,
            action="EMAIL_VERIFIED",
            ip_address=ip_address,
            user_agent=user_agent
        )
        return {"message": "Email address verified successfully. Your account is now active."}
    except UserNotFoundException as e:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except AuthServiceException as e:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/resend-verification")
async def resend_verification(
    request: Request,
    payload: ResendVerifyRequest,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Invalidate any active codes and issue a fresh 6-digit email verification OTP.
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        await VerificationService.resend_verification(db, payload.email)
        
        # Log Audit Log
        user = await UserService.get_user_by_email(db, payload.email)
        await AuditService.log_action(
            db=db,
            user_id=user.id,
            action="VERIFICATION_RESENT",
            ip_address=ip_address,
            user_agent=user_agent
        )
        return {"message": "A new verification code has been generated and printed to the developer console."}
    except UserNotFoundException as e:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except AuthServiceException as e:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/forgot-password")
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Request a password reset link/token for the specified email.
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        await PasswordResetService.request_password_reset(db, payload.email)
        
        # Log Audit Log
        user = await UserService.get_user_by_email(db, payload.email)
        await AuditService.log_action(
            db=db,
            user_id=user.id,
            action="PASSWORD_RESET_REQUESTED",
            ip_address=ip_address,
            user_agent=user_agent
        )
        return {"message": "Password reset token generated and printed to the developer console."}
    except UserNotFoundException:
         # Prevent email discovery by returning a successful status
         return {"message": "Password reset token generated and printed to the developer console."}
    except AuthServiceException as e:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/reset-password")
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Reset user password using a valid reset token.
    Force log out all active sessions on success.
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        # Load user ID prior to resetting token invalidation
        hashed_token = PasswordResetService._hash_token(payload.token)
        from app.repositories.password_reset_repository import PasswordResetRepository
        active_reset = await PasswordResetRepository.get_active_token(db, hashed_token)
        user_id = active_reset.user_id if active_reset else None
        
        await PasswordResetService.reset_password(db, payload.token, payload.new_password)
        
        # Log Audit Log
        if user_id:
            await AuditService.log_action(
                db=db,
                user_id=user_id,
                action="PASSWORD_RESET_SUCCESSFUL",
                ip_address=ip_address,
                user_agent=user_agent
            )
        return {"message": "Password reset successfully. All active sessions have been logged out."}
    except SamePasswordException as e:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except UserNotFoundException as e:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except AuthServiceException as e:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
