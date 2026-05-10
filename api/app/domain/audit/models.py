# api/app/domain/audit/models.py

"""Audit event domain models. Never store sensitive values; log only that a change occurred."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4


class AuditSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AuditCategory(str, Enum):
    SECURITY = "security"
    CONFIGURATION = "configuration"
    ACCESS = "access"
    AUDIT = "audit"


class AuditAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

    REVEAL = "reveal"
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"

    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    SUSPEND = "suspend"

    VIEW = "view"
    ACCESS_DENIED = "access_denied"
    DOWNLOAD = "download"
    TOKEN_REFRESH = "token_refresh"

    INSTALL = "install"
    UNINSTALL = "uninstall"

    INVITE = "invite"
    ROLE_CHANGE = "role_change"

    TRIGGER = "trigger"
    APPROVE = "approve"
    REJECT = "reject"
    BYPASS = "bypass"
    TIMEOUT = "timeout"
    CANCEL = "cancel"
    RETRY = "retry"
    RERUN = "rerun"
    REGENERATE = "regenerate"
    UPLOAD = "upload"


class AuditActorType(str, Enum):
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
    SYSTEM = "system"
    ANONYMOUS = "anonymous"
    UNKNOWN = "unknown"


class AuditStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class ResourceType(str, Enum):
    SECRET = "secret"
    CREDENTIAL = "credential"
    USER = "user"

    ORGANIZATION = "organization"

    WORKFLOW = "workflow"
    BLUEPRINT = "blueprint"
    INSTANCE = "instance"
    INSTANCE_STEP = "instance_step"

    PROVIDER = "provider"
    SERVICE = "service"
    PACKAGE = "package"

    FILE = "file"

    AUDIT_LOG = "audit_log"


@dataclass
class AuditEvent:
    """An auditable event. Never store sensitive values; use changes={'changed': True}."""

    action: AuditAction
    resource_type: ResourceType

    actor_id: Optional[UUID] = None
    actor_type: AuditActorType = AuditActorType.ANONYMOUS

    resource_id: Optional[UUID] = None
    resource_name: Optional[str] = None

    organization_id: Optional[UUID] = None

    severity: AuditSeverity = AuditSeverity.INFO
    category: AuditCategory = AuditCategory.CONFIGURATION

    changes: Optional[Dict[str, Any]] = None

    metadata: Dict[str, Any] = field(default_factory=dict)

    status: AuditStatus = AuditStatus.SUCCESS
    error_message: Optional[str] = None

    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def is_system_event(self) -> bool:
        """True for system-level events (visible only to super_admin)."""
        return self.organization_id is None

    def is_security_event(self) -> bool:
        return self.category == AuditCategory.SECURITY

    def is_critical(self) -> bool:
        return self.severity == AuditSeverity.CRITICAL


def create_secret_audit_event(
    actor_id: UUID,
    actor_type: AuditActorType,
    action: AuditAction,
    organization_id: UUID,
    secret_id: UUID,
    secret_name: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    """Audit event for secret operations. Never includes the secret value."""
    severity = (
        AuditSeverity.CRITICAL if action == AuditAction.REVEAL else AuditSeverity.INFO
    )

    return AuditEvent(
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        resource_type=ResourceType.SECRET,
        resource_id=secret_id,
        resource_name=secret_name,
        organization_id=organization_id,
        severity=severity,
        category=AuditCategory.SECURITY,
        changes={"changed": True} if action == AuditAction.UPDATE else None,
        metadata=metadata or {},
    )


def create_credential_audit_event(
    actor_id: UUID,
    actor_type: AuditActorType,
    action: AuditAction,
    organization_id: UUID,
    credential_id: UUID,
    credential_name: str,
    provider_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    """Audit event for credential operations. Never includes the credential value."""
    event_metadata = metadata or {}
    if provider_name:
        event_metadata["provider_name"] = provider_name

    return AuditEvent(
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        resource_type=ResourceType.CREDENTIAL,
        resource_id=credential_id,
        resource_name=credential_name,
        organization_id=organization_id,
        severity=AuditSeverity.INFO,
        category=AuditCategory.SECURITY,
        changes={"changed": True} if action == AuditAction.UPDATE else None,
        metadata=event_metadata,
    )
