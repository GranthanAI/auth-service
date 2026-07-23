from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from app.core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    future=True,
    pool_pre_ping=True
)
