from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(hide_input_in_errors=True, 
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    DATABASE_URL: str = "postgresql+asyncpg://postgres:1234@localhost:5432/auth_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    
    ENVIRONMENT: str = "development"

    JWT_SECRET_KEY: str = "supersecretjwtkeyforauthservicelocaldvelopment12345"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    
    # CORS Origin List
    ALLOWED_CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Database Settings
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # Security Throttling & Lockout Settings
    # Lockout is per (client IP, email): FAILED_LOGIN_LIMIT failures lock the pair for LOCKOUT_BASE_SECONDS, doubling
    # per further failure up to LOCKOUT_DURATION_SECONDS (also the counting window). FAILED_LOGIN_EMAIL_CEILING is the
    # much higher total across all IPs that locks the account itself.
    FAILED_LOGIN_LIMIT: int = 5
    LOCKOUT_BASE_SECONDS: int = 30
    LOCKOUT_DURATION_SECONDS: int = 1800  # 30 minutes
    FAILED_LOGIN_EMAIL_CEILING: int = 50

    # Rate limits for the unauthenticated email-sending endpoints (per client IP and per target email).
    EMAIL_ENDPOINT_IP_LIMIT: int = 10
    EMAIL_ENDPOINT_IP_WINDOW_SECONDS: int = 3600
    EMAIL_ENDPOINT_EMAIL_LIMIT: int = 3
    EMAIL_ENDPOINT_EMAIL_WINDOW_SECONDS: int = 3600

    # Email verification. OFF by default: sign-up creates an ACTIVE account and the user can log in
    # immediately (no OTP is generated). Set EMAIL_VERIFICATION_REQUIRED=true to restore the original
    # flow: PENDING until the emailed 6-digit code is verified, and login is refused until then.
    # Flipping it to false also lets accounts that are still PENDING log in.
    EMAIL_VERIFICATION_REQUIRED: bool = False

    # Email delivery. "console" logs messages (OTPs, reset links) and is only allowed when ENVIRONMENT is development
    # or test; every other environment must use "smtp". Startup fails fast otherwise.
    EMAIL_SENDER: str = "console"
    EMAIL_FROM: str = "no-reply@granthan.com"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: SecretStr | None = None
    SMTP_STARTTLS: bool = True
    SMTP_USE_SSL: bool = False  # implicit TLS (port 465); takes precedence over STARTTLS
    SMTP_TIMEOUT_SECONDS: float = 10.0
    # Public frontend origin used to build the password-reset link.
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    # Key for hashing stored verification OTPs. Empty = derive from JWT_SECRET_KEY.
    OTP_HMAC_KEY: str = ""

    # Email dispatch worker (reads the email_outbox table)
    EMAIL_WORKER_POLL_INTERVAL_SECONDS: float = 2.0
    EMAIL_BATCH_SIZE: int = 20
    EMAIL_MAX_ATTEMPTS: int = 6
    EMAIL_RETRY_BASE_SECONDS: int = 30
    EMAIL_RETRY_MAX_SECONDS: int = 3600

    # Token Expirations
    OTP_EXPIRE_MINUTES: int = 15
    PASSWORD_RESET_EXPIRE_HOURS: int = 1

    # Outbox Daemon Settings
    OUTBOX_POLL_INTERVAL_SECONDS: float = 2.0
    OUTBOX_BATCH_SIZE: int = 50

    # Kafka Optimization Settings
    KAFKA_LINGER_MS: int = 5

# Instantiated once to act as a global singleton config

    @model_validator(mode="after")
    def _validate_email_config(self):
        from app.email.validation import validate_sender_config
        validate_sender_config(self.EMAIL_SENDER, self.ENVIRONMENT, self.SMTP_HOST)
        return self

    @model_validator(mode="after")
    def _fail_fast_on_unsafe_production_config(self):
        """In production the service refuses to start with a development default or a weak secret (a known default
        would let anyone forge tokens). Development and test environments are unaffected. Secret VALUES are never
        included in the error message."""
        if self.ENVIRONMENT.strip().lower() not in ("production", "prod"):
            return self
        dev_values = {"supersecretjwtkeyforauthservicelocaldvelopment12345", "graphgpt-jwt-secret", "graphgpt-memory-secret", "changeme", "secret"}
        problems: list[str] = []

        def secret(name: str, value: str) -> None:
            if not value or value in dev_values or len(value) < 32:
                problems.append(f"{name} must be set to a unique secret of at least 32 characters")
        secret("JWT_SECRET_KEY", self.JWT_SECRET_KEY)
        if self.JWT_ALGORITHM not in ("HS256", "HS384", "HS512"):
            problems.append("JWT_ALGORITHM must be an HMAC algorithm (HS256/HS384/HS512)")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self


settings = Settings()
