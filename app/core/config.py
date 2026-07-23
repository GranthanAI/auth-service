from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/auth_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    
    JWT_SECRET_KEY: str = "supersecretjwtkeyforauthservicelocaldvelopment12345"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

# Instantiated once to act as a global singleton config
settings = Settings()
