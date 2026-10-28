from app.core.config import settings
from app.email.sender import EmailMessage

KIND_VERIFICATION_OTP = "verification_otp"
KIND_PASSWORD_RESET = "password_reset"


def render(kind: str, to_email: str, payload: dict) -> EmailMessage:
    if kind == KIND_VERIFICATION_OTP:
        return EmailMessage(
            to=to_email,
            subject="Your Granthan verification code",
            body=(
                f"Your Granthan verification code is {payload['code']}.\n\n"
                f"It expires in {settings.OTP_EXPIRE_MINUTES} minutes. If you did not create an account, ignore this email."
            ),
        )
    if kind == KIND_PASSWORD_RESET:
        link = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={payload['token']}"
        return EmailMessage(
            to=to_email,
            subject="Reset your Granthan password",
            body=(
                f"Use the link below to choose a new password:\n\n{link}\n\n"
                f"It expires in {settings.PASSWORD_RESET_EXPIRE_HOURS} hour(s). "
                "If you did not request this, ignore this email; your password is unchanged."
            ),
        )
    raise ValueError(f"unknown email kind: {kind}")
