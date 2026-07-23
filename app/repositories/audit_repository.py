import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

class AuditRepository:
    @staticmethod
    async def create_log_entry(
        db: AsyncSession,
        user_id: uuid.UUID | None,
        action: str,
        ip_address: str | None,
        user_agent: str | None,
        metadata_dict: dict | None
    ) -> AuditLog:
        db_log = AuditLog(
            user_id=user_id,
            action=action,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_json=metadata_dict
        )
        db.add(db_log)
        await db.flush()
        return db_log
