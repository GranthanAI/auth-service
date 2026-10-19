from pydantic import model_validator
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
    FAILED_LOGIN_LIMIT: int = 5
    LOCKOUT_DURATION_SECONDS: int = 1800  # 30 minutes

    # Email verification. OFF by default: sign-up creates an ACTIVE account and the user can log in
    # immediately (no OTP is generated). Set EMAIL_VERIFICATION_REQUIRED=true to restore the original
    # flow: PENDING until the emailed 6-digit code is verified, and login is refused until then.
    # Flipping it to false also lets accounts that are still PENDING log in.
    EMAIL_VERIFICATION_REQUIRED: bool = False

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
