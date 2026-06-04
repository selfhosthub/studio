# api/app/application/services/audit_service.py

"""Audit logging and querying. Sensitive values are NEVER logged - only the
fact that a change occurred."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from contracts.redaction import SENSITIVE_KEYS, is_sensitive_key

from app.domain.audit.models import (
    AuditAction,
    AuditActorType,
    AuditCategory,
    AuditEvent,
    AuditSeverity,
    AuditStatus,
    ResourceType,
)
from app.domain.audit.repository import AuditEventRepository

logger = logging.getLogger(__name__)


# Back-compat alias.
SENSITIVE_FIELDS = SENSITIVE_KEYS


def sanitize_changes(changes: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Replace sensitive-key values with `{"changed": True}` - preserves the
    fact-of-change signal without leaking the value. The placeholder shape lets
    audit logs distinguish "modified" from "static but sensitive"."""
    if not changes:
        return changes

    sanitized = {}
    for key, value in changes.items():
        if isinstance(key, str) and is_sensitive_key(key):
            sanitized[key] = {"changed": True}
        elif isinstance(value, dict):
            sanitized[key] = sanitize_changes(value)
        else:
            sanitized[key] = value

    return sanitized


class AuditService:
    def __init__(self, repository: AuditEventRepository):
        self.repository = repository

    async def log_event(
        self,
        actor_id: Optional[UUID],
        actor_type: AuditActorType,
        action: AuditAction,
        resource_type: ResourceType,
        resource_id: Optional[UUID] = None,
        resource_name: Optional[str] = None,
        organization_id: Optional[UUID] = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        category: AuditCategory = AuditCategory.CONFIGURATION,
        changes: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        status: AuditStatus = AuditStatus.SUCCESS,
        error_message: Optional[str] = None,
    ) -> Optional[AuditEvent]:
        """Persist one audit event. Sensitive values are sanitized before write."""
        safe_changes = sanitize_changes(changes)

        event = AuditEvent(
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            organization_id=organization_id,
            severity=severity,
            category=category,
            changes=safe_changes,
            metadata=metadata or {},
            status=status,
            error_message=error_message,
        )

        try:
            return await self.repository.create(event)
        except Exception as e:
            # Audit failures must never fail the caller's main operation.
            logger.error(f"Failed to create audit event: {type(e).__name__}")
            return None

    async def log_secret_created(
        self,
        actor_id: UUID,
        actor_type: AuditActorType,
        organization_id: UUID,
        secret_id: UUID,
        secret_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditEvent]:
        return await self.log_event(
            actor_id=actor_id,
            actor_type=actor_type,
            action=AuditAction.CREATE,
            resource_type=ResourceType.SECRET,
            resource_id=secret_id,
            resource_name=secret_name,
            organization_id=organization_id,
            severity=AuditSeverity.INFO,
            category=AuditCategory.SECURITY,
            metadata=metadata,
        )

    async def log_secret_updated(
        self,
        actor_id: UUID,
        actor_type: AuditActorType,
        organization_id: UUID,
        secret_id: UUID,
        secret_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditEvent]:
        return await self.log_event(
            actor_id=actor_id,
            actor_type=actor_type,
            action=AuditAction.UPDATE,
            resource_type=ResourceType.SECRET,
            resource_id=secret_id,
            resource_name=secret_name,
            organization_id=organization_id,
            severity=AuditSeverity.INFO,
            category=AuditCategory.SECURITY,
            changes={"value": {"changed": True}},
            metadata=metadata,
        )

    async def log_secret_deleted(
        self,
        actor_id: UUID,
        actor_type: AuditActorType,
        organization_id: UUID,
        secret_id: UUID,
        secret_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditEvent]:
        return await self.log_event(
            actor_id=actor_id,
            actor_type=actor_type,
            action=AuditAction.DELETE,
            resource_type=ResourceType.SECRET,
            resource_id=secret_id,
            resource_name=secret_name,
            organization_id=organization_id,
            severity=AuditSeverity.WARNING,
            category=AuditCategory.SECURITY,
            metadata=metadata,
        )

    async def log_secret_revealed(
        self,
        actor_id: UUID,
        actor_type: AuditActorType,
        organization_id: UUID,
        secret_id: UUID,
        secret_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditEvent]:
        # CRITICAL severity - secret value was viewed.
        return await self.log_event(
            actor_id=actor_id,
            actor_type=actor_type,
            action=AuditAction.REVEAL,
            resource_type=ResourceType.SECRET,
            resource_id=secret_id,
            resource_name=secret_name,
            organization_id=organization_id,
            severity=AuditSeverity.CRITICAL,
            category=AuditCategory.SECURITY,
            metadata=metadata,
        )

    async def log_credential_created(
        self,
        actor_id: UUID,
        actor_type: AuditActorType,
        organization_id: UUID,
        credential_id: UUID,
        credential_name: str,
        provider_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditEvent]:
        event_metadata = metadata or {}
        if provider_name:
            event_metadata["provider_name"] = provider_name

        return await self.log_event(
            actor_id=actor_id,
            actor_type=actor_type,
            action=AuditAction.CREATE,
            resource_type=ResourceType.CREDENTIAL,
            resource_id=credential_id,
            resource_name=credential_name,
            organization_id=organization_id,
            severity=AuditSeverity.INFO,
            category=AuditCategory.SECURITY,
            metadata=event_metadata,
        )

    async def log_credential_updated(
        self,
        actor_id: UUID,
        actor_type: AuditActorType,
        organization_id: UUID,
        credential_id: UUID,
        credential_name: str,
        provider_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditEvent]:
        event_metadata = metadata or {}
        if provider_name:
            event_metadata["provider_name"] = provider_name

        return await self.log_event(
            actor_id=actor_id,
            actor_type=actor_type,
            action=AuditAction.UPDATE,
            resource_type=ResourceType.CREDENTIAL,
            resource_id=credential_id,
            resource_name=credential_name,
            organization_id=organization_id,
            severity=AuditSeverity.INFO,
            category=AuditCategory.SECURITY,
            changes={"value": {"changed": True}},
            metadata=event_metadata,
        )

    async def log_credential_deleted(
        self,
        actor_id: UUID,
        actor_type: AuditActorType,
        organization_id: UUID,
        credential_id: UUID,
        credential_name: str,
        provider_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditEvent]:
        event_metadata = metadata or {}
        if provider_name:
            event_metadata["provider_name"] = provider_name

        return await self.log_event(
            actor_id=actor_id,
            actor_type=actor_type,
            action=AuditAction.DELETE,
            resource_type=ResourceType.CREDENTIAL,
            resource_id=credential_id,
            resource_name=credential_name,
            organization_id=organization_id,
            severity=AuditSeverity.WARNING,
            category=AuditCategory.SECURITY,
            metadata=event_metadata,
        )

    async def log_user_invited(
        self,
        actor_id: UUID,
        actor_type: AuditActorType,
        organization_id: UUID,
        user_id: UUID,
        user_email: str,
        role: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditEvent]:
        event_metadata = metadata or {}
        event_metadata["role"] = role

        return await self.log_event(
            actor_id=actor_id,
            actor_type=actor_type,
            action=AuditAction.INVITE,
            resource_type=ResourceType.USER,
            resource_id=user_id,
            resource_name=user_email,
            organization_id=organization_id,
            severity=AuditSeverity.INFO,
            category=AuditCategory.SECURITY,
            metadata=event_metadata,
        )

    async def log_user_role_changed(
        self,
        actor_id: UUID,
        actor_type: AuditActorType,
        organization_id: UUID,
        user_id: UUID,
        user_email: str,
        old_role: str,
        new_role: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditEvent]:
        return await self.log_event(
            actor_id=actor_id,
            actor_type=actor_type,
            action=AuditAction.ROLE_CHANGE,
            resource_type=ResourceType.USER,
            resource_id=user_id,
            resource_name=user_email,
            organization_id=organization_id,
            severity=AuditSeverity.WARNING,
            category=AuditCategory.SECURITY,
            changes={"role": {"old": old_role, "new": new_role}},
            metadata=metadata,
        )

    async def log_login(
        self,
        actor_id: Optional[UUID],
        actor_type: AuditActorType,
        user_email: str,
        organization_id: Optional[UUID] = None,
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditEvent]:
        action = AuditAction.LOGIN if success else AuditAction.LOGIN_FAILED
        severity = AuditSeverity.INFO if success else AuditSeverity.WARNING

        return await self.log_event(
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            resource_type=ResourceType.USER,
            resource_id=actor_id,
            resource_name=user_email,
            organization_id=organization_id,
            severity=severity,
            category=AuditCategory.SECURITY,
            status=AuditStatus.SUCCESS if success else AuditStatus.FAILED,
            metadata=metadata,
        )

    async def log_audit_log_viewed(
        self,
        actor_id: UUID,
        actor_type: AuditActorType,
        organization_id: Optional[UUID] = None,
        viewed_org_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditEvent]:
        # Audit the auditors.
        event_metadata = metadata or {}
        if viewed_org_id:
            event_metadata["viewed_organization_id"] = str(viewed_org_id)

        return await self.log_event(
            actor_id=actor_id,
            actor_type=actor_type,
            action=AuditAction.VIEW,
            resource_type=ResourceType.AUDIT_LOG,
            organization_id=organization_id,
            severity=AuditSeverity.INFO,
            category=AuditCategory.AUDIT,
            metadata=event_metadata,
        )

    async def log_provider_changed(
        self,
        actor_id: UUID,
        actor_type: AuditActorType,
        action: AuditAction,
        provider_id: UUID,
        provider_name: str,
        changes: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditEvent]:
        # Provider CRUD is system-level - no org_id.
        return await self.log_event(
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            resource_type=ResourceType.PROVIDER,
            resource_id=provider_id,
            resource_name=provider_name,
            organization_id=None,
            severity=(
                AuditSeverity.WARNING
                if action == AuditAction.DELETE
                else AuditSeverity.INFO
            ),
            category=AuditCategory.CONFIGURATION,
            changes=changes,
            metadata=metadata,
        )

    async def log_package_action(
        self,
        actor_id: UUID,
        actor_type: AuditActorType,
        action: AuditAction,
        package_name: str,
        version: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditEvent]:
        # System-level event.
        event_metadata = metadata or {}
        if version:
            event_metadata["version"] = version

        return await self.log_event(
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            resource_type=ResourceType.PACKAGE,
            resource_name=package_name,
            organization_id=None,
            severity=AuditSeverity.WARNING,
            category=AuditCategory.CONFIGURATION,
            metadata=event_metadata,
        )

    async def list_organization_events(
        self,
        organization_id: UUID,
        skip: int = 0,
        limit: int = 50,
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        actor_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[AuditEvent]:
        return await self.repository.list_by_organization(
            organization_id=organization_id,
            skip=skip,
            limit=limit,
            resource_type=resource_type,
            action=action,
            severity=severity,
            category=category,
            actor_id=actor_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def list_system_events(
        self,
        skip: int = 0,
        limit: int = 50,
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        severity: Optional[str] = None,
        actor_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[AuditEvent]:
        # super_admin only.
        return await self.repository.list_system_events(
            skip=skip,
            limit=limit,
            resource_type=resource_type,
            action=action,
            severity=severity,
            actor_id=actor_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def list_all_events(
        self,
        skip: int = 0,
        limit: int = 50,
        organization_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        actor_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_system_events: bool = True,
    ) -> List[AuditEvent]:
        # super_admin only.
        return await self.repository.list_all_events(
            skip=skip,
            limit=limit,
            organization_id=organization_id,
            resource_type=resource_type,
            action=action,
            severity=severity,
            category=category,
            actor_id=actor_id,
            start_date=start_date,
            end_date=end_date,
            include_system_events=include_system_events,
        )

    async def get_resource_history(
        self,
        resource_type: str,
        resource_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> List[AuditEvent]:
        return await self.repository.list_by_resource(
            resource_type=resource_type,
            resource_id=resource_id,
            skip=skip,
            limit=limit,
        )

    async def get_actor_history(
        self,
        actor_id: UUID,
        skip: int = 0,
        limit: int = 50,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[AuditEvent]:
        return await self.repository.list_by_actor(
            actor_id=actor_id,
            skip=skip,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )

    async def count_events(
        self,
        organization_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        return await self.repository.count_all(
            organization_id=organization_id,
            resource_type=resource_type,
            severity=severity,
            category=category,
            start_date=start_date,
            end_date=end_date,
        )
