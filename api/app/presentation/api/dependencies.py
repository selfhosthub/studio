# api/app/presentation/api/dependencies.py

"""FastAPI dependency injection wiring for all API endpoints."""

from typing import Any, AsyncGenerator, Optional
from uuid import UUID

from fastapi import Depends, Request, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import TypedDict

from app.application.interfaces.event_bus import EventBus
from app.application.services.audit_service import AuditService
from app.application.services.package_management_service import PackageManagementService
from app.application.services.public_content_service import PublicContentService
from app.application.services.system_health_service import SystemHealthService
from app.application.services.instance_service import InstanceService
from app.application.services.org_file import (
    OrgFileService,
)
from app.application.services.notification_service import NotificationService
from app.application.services.site_content_service import SiteContentService
from app.application.services.organization import OrganizationService
from app.application.services.provider_service import (
    ProviderService as ProviderServiceClass,
)
from app.application.services.queue_service import QueueService
from app.application.services.blueprint_service import BlueprintService
from app.application.services.webhook_service import WebhookService
from app.application.services.workflow_service import WorkflowService
from app.domain.common.value_objects import Role
from app.domain.instance.repository import InstanceRepository
from app.domain.org_file.repository import OrgFileRepository
from app.domain.notification.repository import NotificationRepository
from app.domain.site_content.repository import SiteContentRepository
from app.domain.organization.repository import (
    OrganizationRepository,
    UserRepository,
)
from app.domain.provider.repository import (
    ProviderCredentialRepository,
    ProviderRepository,
    ProviderServiceRepository,
)
from app.domain.queue.repository import (
    QueuedJobRepository,
    QueueRepository,
    WorkerRepository,
)
from app.domain.prompt.repository import PromptRepository
from app.domain.blueprint.repository import BlueprintRepository
from app.domain.workflow.repository import WorkflowRepository
from app.infrastructure.auth.jwt import RoleChecker, get_current_user
from app.infrastructure.auth.password_service import PasswordService
from app.infrastructure.messaging.event_bus import InMemoryEventBus
from app.infrastructure.messaging.job_status_publisher import DirectJobStatusPublisher
from app.infrastructure.persistence.database import (
    get_db_session,
    get_db_session_service,
    get_db_session_with_rls,
)
from app.infrastructure.repositories.instance_repository import (
    SQLAlchemyInstanceRepository,
)
from app.infrastructure.repositories.audit_repository import AuditEventRepository
from app.infrastructure.repositories.org_file_repository import (
    SQLAlchemyOrgFileRepository,
)
from app.infrastructure.repositories.step_execution_repository import (
    SQLAlchemyStepExecutionRepository,
)
from app.domain.instance_step.step_execution_repository import StepExecutionRepository
from app.infrastructure.repositories.iteration_execution_repository import (
    SQLAlchemyIterationExecutionRepository,
)
from app.infrastructure.repositories.notification_repository import (
    SQLAlchemyNotificationRepository,
)
from app.infrastructure.repositories.site_content_repository import (
    SQLAlchemySiteContentRepository,
)
from app.infrastructure.repositories.organization_repository import (
    SQLAlchemyOrganizationRepository,
    SQLAlchemyUserRepository,
)
from app.infrastructure.repositories.provider_repository import (
    SQLAlchemyProviderCredentialRepository,
    SQLAlchemyProviderRepository,
    SQLAlchemyProviderServiceRepository,
)
from app.infrastructure.repositories.queue_job_repository import (
    SQLAlchemyQueuedJobRepository,
)
from app.infrastructure.repositories.queue_repository import (
    SQLAlchemyQueueRepository,
)
from app.infrastructure.repositories.prompt_repository import (
    SQLAlchemyPromptRepository,
)
from app.infrastructure.repositories.blueprint_repository import (
    SQLAlchemyBlueprintRepository,
)
from app.infrastructure.repositories.worker_repository import (
    SQLAlchemyWorkerRepository,
)
from app.infrastructure.repositories.workflow_repository import (
    SQLAlchemyWorkflowRepository,
)
from app.infrastructure.repositories.organization_secret_repository import (
    SQLAlchemyOrganizationSecretRepository,
)
from app.infrastructure.repositories.marketplace_catalog_repository import (
    SQLAlchemyMarketplaceCatalogRepository,
)
from app.domain.organization_secret.repository import OrganizationSecretRepository
from app.application.services.job_enqueue import JobEnqueueService
from app.domain.provider.models import PackageType
from app.infrastructure.persistence.models import PackageVersionModel
from app.infrastructure.services.package_version_service import PackageVersionService
from app.application.services.prompt_service import PromptService
from app.infrastructure.adapters.registry import AdapterRegistry


class CurrentUser(TypedDict):
    id: str
    username: Optional[str]
    email: Optional[str]
    role: Optional[str]
    org_id: Optional[str]
    org_slug: Optional[str]


_event_bus = InMemoryEventBus()

# Register event handlers
from app.application.event_handlers import register_event_handlers

register_event_handlers(_event_bus)

# WebSocket event handler registration is deferred to avoid a circular import
# chain that forms when the handler modules are loaded at import time.
# Call init_ws_event_handlers() after all modules are loaded.


def init_ws_event_handlers():
    """Must be called after all modules are loaded to avoid circular imports."""
    from app.presentation.websockets.handlers import (
        register_event_handlers as register_ws_event_handlers,
    )

    register_ws_event_handlers(_event_bus)


def get_event_bus() -> EventBus:
    return _event_bus


def get_adapter_registry() -> AdapterRegistry:
    """Initialized at startup; imported lazily to avoid circular import."""
    from main import adapter_registry

    return adapter_registry


def _get_status_publisher(conn: Request | WebSocket) -> DirectJobStatusPublisher:
    """Create a status publisher wired to the result processor."""
    result_processor = getattr(conn.app.state, "result_processor", None)
    if result_processor is None:
        raise RuntimeError("result_processor not initialized on app.state")
    return DirectJobStatusPublisher(result_processor.process_result)


def get_notifier(request: Request):
    """Get the notifier singleton from app state."""
    notifier = getattr(request.app.state, "notifier", None)
    if notifier is None:
        raise RuntimeError("InstanceNotifier not initialized on app.state")
    return notifier


# =============================================================================
# RLS-aware Database Session Dependencies
# =============================================================================


async def get_db_session_rls(
    user: dict[str, Any] = Depends(get_current_user),
) -> AsyncGenerator[AsyncSession, None]:
    """Session with RLS context set from the authenticated user's org."""
    async for session in get_db_session_with_rls(user):
        yield session


async def get_db_session_bypass_rls(
    user: dict[str, Any] = Depends(get_current_user),
) -> AsyncGenerator[AsyncSession, None]:
    """Session WITHOUT RLS. Only for super_admin cross-org endpoints - must be paired with a super_admin role check."""
    async for session in get_db_session():
        yield session


# =============================================================================
# Repository Dependencies (using RLS-aware sessions for authenticated endpoints)
# =============================================================================


async def get_organization_repository(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[OrganizationRepository, None]:
    """Organizations table is NOT RLS-protected; uses plain session."""
    yield SQLAlchemyOrganizationRepository(session)


async def get_user_repository(
    session: AsyncSession = Depends(get_db_session_rls),
) -> AsyncGenerator[UserRepository, None]:
    yield SQLAlchemyUserRepository(session)


async def get_user_repository_bypass(
    session: AsyncSession = Depends(get_db_session_service),
) -> AsyncGenerator[UserRepository, None]:
    """Without RLS. Only for auth (pre-authentication lookup) and super_admin cross-org access."""
    yield SQLAlchemyUserRepository(session)


async def get_workflow_repository(
    session: AsyncSession = Depends(get_db_session_rls),
) -> AsyncGenerator[WorkflowRepository, None]:
    yield SQLAlchemyWorkflowRepository(session)


async def get_blueprint_repository(
    session: AsyncSession = Depends(get_db_session_rls),
) -> AsyncGenerator[BlueprintRepository, None]:
    yield SQLAlchemyBlueprintRepository(session)


async def get_provider_repository(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[ProviderRepository, None]:
    yield SQLAlchemyProviderRepository(session)


async def get_provider_service_repository(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[ProviderServiceRepository, None]:
    yield SQLAlchemyProviderServiceRepository(session)


async def get_provider_credential_repository(
    session: AsyncSession = Depends(get_db_session_rls),
) -> AsyncGenerator[ProviderCredentialRepository, None]:
    yield SQLAlchemyProviderCredentialRepository(session)


async def get_instance_repository(
    session: AsyncSession = Depends(get_db_session_rls),
) -> AsyncGenerator[InstanceRepository, None]:
    yield SQLAlchemyInstanceRepository(session)


async def get_step_execution_repository(
    session: AsyncSession = Depends(get_db_session_rls),
) -> AsyncGenerator[StepExecutionRepository, None]:
    """step_executions is not directly RLS-protected; access is scoped via instance FK."""
    yield SQLAlchemyStepExecutionRepository(session)


async def get_notification_repository(
    session: AsyncSession = Depends(get_db_session_rls),
) -> AsyncGenerator[NotificationRepository, None]:
    yield SQLAlchemyNotificationRepository(session)


async def get_site_content_repository(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[SiteContentRepository, None]:
    """site_content is NOT RLS-protected (system-wide)."""
    yield SQLAlchemySiteContentRepository(session)


async def get_queue_repository(
    session: AsyncSession = Depends(get_db_session_rls),
) -> AsyncGenerator[QueueRepository, None]:
    yield SQLAlchemyQueueRepository(session)


async def get_queue_repository_bypass(
    session: AsyncSession = Depends(get_db_session_service),
) -> AsyncGenerator[QueueRepository, None]:
    """Without RLS. Only for worker registration/heartbeat (shared-secret auth, not JWT)."""
    yield SQLAlchemyQueueRepository(session)


async def get_worker_repository(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[WorkerRepository, None]:
    """Workers table is NOT RLS-protected (shared infrastructure)."""
    yield SQLAlchemyWorkerRepository(session)


async def get_queued_job_repository(
    session: AsyncSession = Depends(get_db_session_rls),
) -> AsyncGenerator[QueuedJobRepository, None]:
    yield SQLAlchemyQueuedJobRepository(session)


async def get_queued_job_repository_bypass(
    session: AsyncSession = Depends(get_db_session_service),
) -> AsyncGenerator[QueuedJobRepository, None]:
    """Without RLS. Only for worker endpoints (shared-secret auth, not JWT)."""
    yield SQLAlchemyQueuedJobRepository(session)


async def get_org_file_repository(
    session: AsyncSession = Depends(get_db_session_rls),
) -> AsyncGenerator[OrgFileRepository, None]:
    yield SQLAlchemyOrgFileRepository(session)


async def get_organization_secret_repository(
    session: AsyncSession = Depends(get_db_session_rls),
) -> AsyncGenerator[OrganizationSecretRepository, None]:
    yield SQLAlchemyOrganizationSecretRepository(session)


async def get_organization_secret_repository_bypass(
    session: AsyncSession = Depends(get_db_session_service),
) -> AsyncGenerator[OrganizationSecretRepository, None]:
    """Without RLS. Only for marketplace entitlement token lookup (cross-org)."""
    yield SQLAlchemyOrganizationSecretRepository(session)


async def get_marketplace_catalog_repository(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[SQLAlchemyMarketplaceCatalogRepository, None]:
    """Marketplace catalogs are NOT RLS-protected (system-wide)."""
    yield SQLAlchemyMarketplaceCatalogRepository(session)


async def get_provider_credential_repository_bypass(
    session: AsyncSession = Depends(get_db_session_service),
) -> AsyncGenerator[ProviderCredentialRepository, None]:
    """Without RLS. Only for worker endpoints and OAuth callbacks (no user context yet)."""
    yield SQLAlchemyProviderCredentialRepository(session)


async def get_provider_repository_bypass(
    session: AsyncSession = Depends(get_db_session_service),
) -> AsyncGenerator[ProviderRepository, None]:
    """Without RLS. Only for worker credential endpoints and OAuth callbacks."""
    yield SQLAlchemyProviderRepository(session)


def get_password_service() -> PasswordService:
    return PasswordService()


async def get_organization_service(
    organization_repo: OrganizationRepository = Depends(get_organization_repository),
    user_repo: UserRepository = Depends(get_user_repository),
    event_bus: EventBus = Depends(get_event_bus),
    password_service: PasswordService = Depends(get_password_service),
) -> OrganizationService:
    return OrganizationService(
        organization_repository=organization_repo,
        user_repository=user_repo,
        event_bus=event_bus,
        password_service=password_service,
    )


async def get_workflow_service(
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
    event_bus: EventBus = Depends(get_event_bus),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
) -> WorkflowService:
    return WorkflowService(
        workflow_repository=workflow_repo,
        event_bus=event_bus,
        provider_repository=provider_repo,
    )


async def get_blueprint_service(
    blueprint_repo: BlueprintRepository = Depends(get_blueprint_repository),
    organization_repo: OrganizationRepository = Depends(get_organization_repository),
    event_bus: EventBus = Depends(get_event_bus),
) -> BlueprintService:
    return BlueprintService(
        blueprint_repository=blueprint_repo,
        organization_repository=organization_repo,
        event_bus=event_bus,
    )


async def get_provider_service(
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    credential_repo: ProviderCredentialRepository = Depends(
        get_provider_credential_repository
    ),
    event_bus: EventBus = Depends(get_event_bus),
    provider_service_repo: ProviderServiceRepository = Depends(
        get_provider_service_repository
    ),
) -> ProviderServiceClass:
    return ProviderServiceClass(
        provider_repo=provider_repo,
        credential_repo=credential_repo,
        event_bus=event_bus,
        provider_service_repo=provider_service_repo,
    )


async def get_instance_service(
    request: Request,
    instance_repo: InstanceRepository = Depends(get_instance_repository),
    step_execution_repo: StepExecutionRepository = Depends(
        get_step_execution_repository
    ),
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
    organization_repo: OrganizationRepository = Depends(get_organization_repository),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    provider_service_repo: ProviderServiceRepository = Depends(
        get_provider_service_repository
    ),
    credential_repo: ProviderCredentialRepository = Depends(
        get_provider_credential_repository
    ),
    resource_repo: OrgFileRepository = Depends(
        get_org_file_repository
    ),
    event_bus: EventBus = Depends(get_event_bus),
    session: AsyncSession = Depends(get_db_session),
) -> InstanceService:
    # Uses same session for consistency within request
    workflow_repo_for_enqueue = SQLAlchemyWorkflowRepository(session)
    queued_job_repo = SQLAlchemyQueuedJobRepository(session)
    iteration_execution_repo = SQLAlchemyIterationExecutionRepository(session)
    prompt_repo = SQLAlchemyPromptRepository(session)
    prompt_service = PromptService(repository=prompt_repo)
    status_publisher = _get_status_publisher(request)
    job_enqueue_service = JobEnqueueService(
        workflow_repository=workflow_repo_for_enqueue,
        credential_repository=credential_repo,
        provider_repository=provider_repo,
        provider_service_repository=provider_service_repo,
        organization_repository=organization_repo,
        queued_job_repository=queued_job_repo,
        prompt_service=prompt_service,
        status_publisher=status_publisher,
        iteration_execution_repository=iteration_execution_repo,
        step_execution_repository=step_execution_repo,
    )

    return InstanceService(
        instance_repository=instance_repo,
        step_execution_repository=step_execution_repo,
        workflow_repository=workflow_repo,
        organization_repository=organization_repo,
        event_bus=event_bus,
        provider_repository=provider_repo,
        credential_repository=credential_repo,
        job_enqueue_service=job_enqueue_service,
        resource_repository=resource_repo,
        queued_job_repository=queued_job_repo,
        iteration_execution_repository=iteration_execution_repo,
        notifier=getattr(request.app.state, "notifier", None),
    )


async def get_instance_service_bypass(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
) -> InstanceService:
    """Without RLS. Only for public webhook endpoints; security enforced by token lookup."""
    # Create all repositories without RLS
    instance_repo = SQLAlchemyInstanceRepository(session)
    step_execution_repo = SQLAlchemyStepExecutionRepository(session)
    workflow_repo = SQLAlchemyWorkflowRepository(session)
    organization_repo = SQLAlchemyOrganizationRepository(session)
    provider_repo = SQLAlchemyProviderRepository(session)
    provider_service_repo = SQLAlchemyProviderServiceRepository(session)
    credential_repo = SQLAlchemyProviderCredentialRepository(session)
    queued_job_repo = SQLAlchemyQueuedJobRepository(session)
    step_execution_repo = SQLAlchemyStepExecutionRepository(session)

    pt_repo = SQLAlchemyPromptRepository(session)
    pt_service = PromptService(repository=pt_repo)
    iteration_execution_repo = SQLAlchemyIterationExecutionRepository(session)
    status_publisher = _get_status_publisher(request)
    job_enqueue_service = JobEnqueueService(
        workflow_repository=workflow_repo,
        credential_repository=credential_repo,
        provider_repository=provider_repo,
        provider_service_repository=provider_service_repo,
        organization_repository=organization_repo,
        queued_job_repository=queued_job_repo,
        prompt_service=pt_service,
        status_publisher=status_publisher,
        iteration_execution_repository=iteration_execution_repo,
        step_execution_repository=step_execution_repo,
    )

    return InstanceService(
        instance_repository=instance_repo,
        step_execution_repository=step_execution_repo,
        workflow_repository=workflow_repo,
        organization_repository=organization_repo,
        event_bus=event_bus,
        provider_repository=provider_repo,
        credential_repository=credential_repo,
        job_enqueue_service=job_enqueue_service,
        queued_job_repository=queued_job_repo,
        iteration_execution_repository=iteration_execution_repo,
        notifier=getattr(request.app.state, "notifier", None),
    )


async def get_notification_service(
    notification_repo: NotificationRepository = Depends(get_notification_repository),
    event_bus: EventBus = Depends(get_event_bus),
) -> NotificationService:
    return NotificationService(notification_repo, event_bus)


async def get_site_content_service(
    repo: SiteContentRepository = Depends(get_site_content_repository),
) -> SiteContentService:
    return SiteContentService(repo=repo)


async def get_org_file_service(
    resource_repo: OrgFileRepository = Depends(
        get_org_file_repository
    ),
    instance_repo: InstanceRepository = Depends(get_instance_repository),
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
    event_bus: EventBus = Depends(get_event_bus),
) -> OrgFileService:
    return OrgFileService(
        resource_repository=resource_repo,
        instance_repository=instance_repo,
        workflow_repository=workflow_repo,
        event_bus=event_bus,
    )


async def get_org_file_service_bypass(
    session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
) -> OrgFileService:
    """Without RLS. Only for worker endpoints authenticating via X-Worker-Secret header."""
    resource_repo = SQLAlchemyOrgFileRepository(session)
    instance_repo = SQLAlchemyInstanceRepository(session)
    workflow_repo = SQLAlchemyWorkflowRepository(session)

    return OrgFileService(
        resource_repository=resource_repo,
        instance_repository=instance_repo,
        workflow_repository=workflow_repo,
        event_bus=event_bus,
    )


async def get_queue_service(
    queue_repo: QueueRepository = Depends(get_queue_repository),
    worker_repo: WorkerRepository = Depends(get_worker_repository),
    step_execution_repo: QueuedJobRepository = Depends(get_queued_job_repository),
    event_bus: EventBus = Depends(get_event_bus),
) -> QueueService:
    return QueueService(
        queue_repository=queue_repo,
        worker_repository=worker_repo,
        step_execution_repository=step_execution_repo,
        event_bus=event_bus,
    )


async def get_queue_service_bypass(
    queue_repo: QueueRepository = Depends(get_queue_repository_bypass),
    worker_repo: WorkerRepository = Depends(get_worker_repository),
    step_execution_repo: QueuedJobRepository = Depends(
        get_queued_job_repository_bypass
    ),
    event_bus: EventBus = Depends(get_event_bus),
) -> QueueService:
    """Without RLS. Only for worker registration/heartbeat (shared-secret auth, not JWT)."""
    return QueueService(
        queue_repository=queue_repo,
        worker_repository=worker_repo,
        step_execution_repository=step_execution_repo,
        event_bus=event_bus,
    )


async def get_audit_service(
    session: AsyncSession = Depends(get_db_session),
) -> AuditService:
    repository = AuditEventRepository(session)
    return AuditService(repository)


async def get_public_content_service(
    org_repo: OrganizationRepository = Depends(get_organization_repository),
    user_repo: UserRepository = Depends(get_user_repository_bypass),
    site_content_repo: SiteContentRepository = Depends(get_site_content_repository),
) -> PublicContentService:
    """For unauthenticated endpoints; uses bypass repo since no user context exists yet."""
    return PublicContentService(
        organization_repo=org_repo,
        user_repo=user_repo,
        site_content_repo=site_content_repo,
    )


async def get_system_health_service(
    session: AsyncSession = Depends(get_db_session),
) -> SystemHealthService:
    return SystemHealthService(session=session)


async def get_package_management_service(
    session: AsyncSession = Depends(get_db_session),
) -> PackageManagementService:
    return PackageManagementService(session=session)


async def get_active_provider_package_versions(
    session: AsyncSession = Depends(get_db_session),
) -> list[PackageVersionModel]:
    return await PackageVersionService.list_active(session, PackageType.PROVIDER)


async def get_webhook_service_public(
    session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
    instance_service: InstanceService = Depends(get_instance_service_bypass),
) -> WebhookService:
    """Without RLS. Only for public webhook endpoints; security enforced by token lookup."""
    workflow_repository = SQLAlchemyWorkflowRepository(session)

    return WebhookService(
        workflow_repository=workflow_repository,
        instance_service=instance_service,
        event_bus=event_bus,
    )


def get_effective_org_id(
    request_org_id: Optional[str],
    user: CurrentUser,
) -> str:
    """Resolve org_id for a request. Even super_admin cannot cross org boundaries for operational data."""
    from fastapi import HTTPException, status

    user_org_id = user.get("org_id")

    if not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no associated organization",
        )

    if request_org_id is None:
        return user_org_id

    if request_org_id == user_org_id:
        return request_org_id

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Cannot operate on a different organization",
    )


async def _log_access_denied_org_audit(
    user: CurrentUser, requested_org_id: str
) -> None:
    """Log organization access denied to audit DB."""
    try:
        from app.domain.audit.models import (
            AuditAction,
            AuditActorType,
            AuditCategory,
            AuditSeverity,
            AuditStatus,
            ResourceType,
        )
        from uuid import UUID

        user_id_str = user.get("id") or user.get("sub") or ""
        user_org_id = user.get("org_id")

        async for session in get_db_session():
            repo = AuditEventRepository(session)
            svc = AuditService(repo)
            await svc.log_event(
                actor_id=UUID(str(user_id_str)) if user_id_str else None,
                actor_type=AuditActorType(user.get("role") or "user"),
                action=AuditAction.ACCESS_DENIED,
                resource_type=ResourceType.ORGANIZATION,
                organization_id=UUID(user_org_id) if user_org_id else None,
                severity=AuditSeverity.WARNING,
                category=AuditCategory.SECURITY,
                status=AuditStatus.FAILED,
                error_message=f"Org '{user_org_id}' cannot access org '{requested_org_id}'",
                metadata={
                    "denial_type": "organization",
                    "user_org_id": str(user_org_id) if user_org_id else None,
                    "requested_org_id": requested_org_id,
                },
            )
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "Failed to log access denied org audit event"
        )


async def validate_organization_access(organization_id: str, user: CurrentUser) -> None:
    """Hard org boundary - even super_admin cannot access another org's operational data."""
    from fastapi import HTTPException, status

    user_org_id = user.get("org_id")

    if user_org_id != organization_id:
        await _log_access_denied_org_audit(user, organization_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this organization",
        )


async def validate_organization_access_or_super_admin(
    organization_id: str, user: CurrentUser
) -> None:
    """Like validate_organization_access but super_admin may pass through for read-only support access."""
    from fastapi import HTTPException, status

    user_org_id = user.get("org_id")
    user_role = user.get("role", "")

    if user_role == Role.SUPER_ADMIN:
        return

    if user_org_id != organization_id:
        await _log_access_denied_org_audit(user, organization_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this organization",
        )


async def verify_org_access(
    organization_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> UUID:
    """Dependency for org_id path param. Super_admin passes; others restricted to own org."""
    await validate_organization_access_or_super_admin(str(organization_id), user)
    return organization_id


async def verify_org_access_strict(
    organization_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> UUID:
    """Strict variant - even super_admin cannot cross org boundaries."""
    await validate_organization_access(str(organization_id), user)
    return organization_id


# =============================================================================
# WebSocket Dependencies (No OAuth2PasswordBearer - handles auth manually)
# =============================================================================


async def get_instance_service_for_ws(
    websocket: WebSocket,
    session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
) -> InstanceService:
    """
    WebSocket variant. Takes WebSocket not Request - FastAPI does not inject Request for WS endpoints.
    Auth is handled by the WS handler; all authorization checks are the handler's responsibility.
    """
    # Create all repositories without RLS (WebSocket auth is handled separately)
    instance_repo = SQLAlchemyInstanceRepository(session)
    step_execution_repo = SQLAlchemyStepExecutionRepository(session)
    workflow_repo = SQLAlchemyWorkflowRepository(session)
    organization_repo = SQLAlchemyOrganizationRepository(session)
    provider_repo = SQLAlchemyProviderRepository(session)
    provider_service_repo = SQLAlchemyProviderServiceRepository(session)
    credential_repo = SQLAlchemyProviderCredentialRepository(session)
    queued_job_repo = SQLAlchemyQueuedJobRepository(session)
    step_execution_repo = SQLAlchemyStepExecutionRepository(session)

    pt_repo2 = SQLAlchemyPromptRepository(session)
    pt_service2 = PromptService(repository=pt_repo2)
    iteration_execution_repo = SQLAlchemyIterationExecutionRepository(session)
    status_publisher = _get_status_publisher(websocket)
    job_enqueue_service = JobEnqueueService(
        workflow_repository=workflow_repo,
        credential_repository=credential_repo,
        provider_repository=provider_repo,
        provider_service_repository=provider_service_repo,
        organization_repository=organization_repo,
        queued_job_repository=queued_job_repo,
        prompt_service=pt_service2,
        status_publisher=status_publisher,
        iteration_execution_repository=iteration_execution_repo,
        step_execution_repository=step_execution_repo,
    )

    return InstanceService(
        instance_repository=instance_repo,
        step_execution_repository=step_execution_repo,
        workflow_repository=workflow_repo,
        organization_repository=organization_repo,
        event_bus=event_bus,
        provider_repository=provider_repo,
        credential_repository=credential_repo,
        job_enqueue_service=job_enqueue_service,
        iteration_execution_repository=iteration_execution_repo,
        notifier=getattr(websocket.app.state, "notifier", None),
    )


async def get_organization_service_for_ws(
    session: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
) -> OrganizationService:
    """WebSocket variant without RLS; auth and authorization handled by the WS handler."""
    # Create repositories without RLS
    organization_repo = SQLAlchemyOrganizationRepository(session)
    user_repo = SQLAlchemyUserRepository(session)

    return OrganizationService(
        organization_repository=organization_repo,
        user_repository=user_repo,
        event_bus=event_bus,
        password_service=PasswordService(),
    )


# =============================================================================
# Prompt Dependencies
# =============================================================================


async def get_prompt_repository(
    session: AsyncSession = Depends(get_db_session_rls),
) -> AsyncGenerator[PromptRepository, None]:
    yield SQLAlchemyPromptRepository(session)


async def get_prompt_service(
    repo: PromptRepository = Depends(get_prompt_repository),
) -> PromptService:
    return PromptService(repository=repo)


# =============================================================================
# Worker Authentication Dependencies
# =============================================================================

import logging as _logging

from fastapi import Header

from app.config.settings import settings

_worker_logger = _logging.getLogger(__name__)

WORKER_SHARED_SECRET = settings.WORKER_SHARED_SECRET


def verify_worker_secret(
    x_worker_secret: str = Header(..., alias="X-Worker-Secret"),
) -> None:
    """Validates X-Worker-Secret header. Workers use this instead of JWT."""
    from fastapi import HTTPException, status

    if not WORKER_SHARED_SECRET:
        _worker_logger.error("WORKER_SHARED_SECRET not configured on API server")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Worker authentication not configured",
        )

    if x_worker_secret != WORKER_SHARED_SECRET:
        _worker_logger.warning("Invalid worker secret attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid worker secret",
        )


# Role-based access control dependencies with explicit type annotations
require_super_admin: RoleChecker = RoleChecker(allowed_roles=[Role.SUPER_ADMIN])
require_admin: RoleChecker = RoleChecker(allowed_roles=[Role.ADMIN, Role.SUPER_ADMIN])
require_user: RoleChecker = RoleChecker(
    allowed_roles=[Role.USER, Role.ADMIN, Role.SUPER_ADMIN]
)


def require_tenant(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Block super_admin from tenant-scoped operations (e.g. running instances).

    Super admins manage the platform - they don't own tenant data. Attach this
    dependency to any endpoint where super_admin execution would violate tenant
    isolation.
    """
    from fastapi import HTTPException, status

    if user.get("role") == "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admins cannot perform tenant operations",
        )
    return user
