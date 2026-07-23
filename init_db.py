import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.db.base import Base

# Import all models to ensure they register on the Base metadata
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.models.session import Session
from app.models.email_verification import EmailVerification
from app.models.password_reset import PasswordReset
from app.models.audit_log import AuditLog

from app.core.config import settings

async def create_database_if_not_exists():
    # Parse DB URL to connect to the default 'postgres' database
    base_url, db_name = settings.DATABASE_URL.rsplit("/", 1)
    postgres_url = f"{base_url}/postgres"
    
    print(f"Connecting to {postgres_url} to check if database '{db_name}' exists...")
    temp_engine = create_async_engine(postgres_url, isolation_level="AUTOCOMMIT")
    
    async with temp_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
            {"dbname": db_name}
        )
        exists = result.scalar()
        if not exists:
            print(f"Database '{db_name}' does not exist. Creating database '{db_name}'...")
            await conn.execute(text(f"CREATE DATABASE {db_name}"))
            print(f"Database '{db_name}' created successfully.")
        else:
            print(f"Database '{db_name}' already exists.")
            
    await temp_engine.dispose()

async def create_tables():
    print(f"Connecting to {settings.DATABASE_URL} to create tables...")
    engine = create_async_engine(settings.DATABASE_URL)
    
    async with engine.begin() as conn:
        print("Creating all tables in metadata...")
        await conn.run_sync(Base.metadata.create_all)
        print("Tables created successfully.")
        
    await engine.dispose()

async def main():
    try:
        await create_database_if_not_exists()
        await create_tables()
        print("Database initialization completed successfully.")
    except Exception as e:
        print(f"Error during database initialization: {e}")

if __name__ == "__main__":
    asyncio.run(main())
