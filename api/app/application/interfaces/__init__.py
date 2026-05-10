# api/app/application/interfaces/__init__.py

"""Application layer interface exports."""

# Domain exceptions (re-exported for convenience)
from app.domain.common.exceptions import (
    EntityNotFoundError,
    RepositoryError,
    BusinessRuleViolation,
    DomainException,
)

# Application exceptions (re-exported from domain via .exceptions)
from .exceptions import (
    AuthorizationError,
    ConcurrencyError,
    DuplicateEntityError,
    PermissionDeniedError,
    ValidationError,
)

# Service interfaces
from .service_interfaces import (
    InstanceServiceInterface,
    NotificationServiceInterface,
    OrganizationServiceInterface,
    ProviderServiceInterface,
    QueueServiceInterface,
    BlueprintServiceInterface,
    WebhookServiceInterface,
    WorkflowServiceInterface,
)

# Password service interface
from .password_service import PasswordServiceInterface

# Event and message interfaces
from .event_bus import EventBus
from .message_queue import MessageQueue

# Provider adapter interfaces
from .provider_adapter import (
    IProviderAdapter,
    ProviderExecutionResult,
    CredentialValidationResult,
    HealthCheckResult,
)

__all__ = [
    # Domain exceptions (re-exported)
    "EntityNotFoundError",
    "RepositoryError",
    "BusinessRuleViolation",
    "DomainException",
    # Application exceptions (re-exported from domain)
    "AuthorizationError",
    "ConcurrencyError",
    "DuplicateEntityError",
    "PermissionDeniedError",
    "ValidationError",
    # Service interfaces
    "InstanceServiceInterface",
    "NotificationServiceInterface",
    "OrganizationServiceInterface",
    "ProviderServiceInterface",
    "QueueServiceInterface",
    "BlueprintServiceInterface",
    "WebhookServiceInterface",
    "WorkflowServiceInterface",
    # Password service interface
    "PasswordServiceInterface",
    # Event and message interfaces
    "EventBus",
    "MessageQueue",
    # Provider adapter interfaces
    "IProviderAdapter",
    "ProviderExecutionResult",
    "CredentialValidationResult",
    "HealthCheckResult",
]
