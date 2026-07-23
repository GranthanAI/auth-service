import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.audit_repository import AuditRepository
from app.models.audit_log import AuditLog

class AuditService:
    @staticmethod
    async def log_action(
        db: AsyncSession,
        user_id: uuid.UUID | None,
        action: str,
        ip_address: str | None,
        user_agent: str | None,
        metadata_dict: dict | None = None
    ) -> AuditLog:
        """
        Record a security or lifecycle operation into the audit log.
        """
        return await AuditRepository.create_log_entry(
            db=db,
            user_id=user_id,
            action=action,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_dict=metadata_dict
        )
