from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    DATABASE_URL: str = "postgresql+asyncpg://postgres:1234@localhost:5432/auth_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    
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

    # Token Expirations
    OTP_EXPIRE_MINUTES: int = 15
    PASSWORD_RESET_EXPIRE_HOURS: int = 1

    # Outbox Daemon Settings
    OUTBOX_POLL_INTERVAL_SECONDS: float = 2.0
    OUTBOX_BATCH_SIZE: int = 50

    # Kafka Optimization Settings
    KAFKA_LINGER_MS: int = 5

# Instantiated once to act as a global singleton config
settings = Settings()
