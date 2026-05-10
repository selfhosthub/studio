# api/app/presentation/api/providers.py

"""Provider management API endpoints. Providers are system-wide; credentials and services are org-scoped."""

from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Union
from uuid import UUID

logger = logging.getLogger(__name__)


def validate_safe_slug(slug: str, field_name: str = "slug") -> str:
    """Reject slugs with path traversal patterns (/, \\, .., null bytes) before using in filesystem paths."""
    if not slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name}: cannot be empty",
        )

    if ".." in slug or "/" in slug or "\\" in slug or "\x00" in slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name}: contains illegal characters",
        )

    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$", slug):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name}: must contain only alphanumeric characters, dashes, underscores, and dots",
        )

    return slug


from app.config.settings import settings
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, UUID4

from app.application.dtos.provider_dto import (
    ProviderCreate,
    ProviderCredentialCreate,
    ProviderCredentialUpdate,
    ProviderServiceCreate,
    ProviderServiceUpdate,
    ProviderUpdate,
)
from app.application.interfaces import EntityNotFoundError
from app.application.services.provider_service import (
    ProviderService as ProviderServiceClass,
)
from app.domain.provider.models import CredentialType, PackageType, ProviderStatus
from app.domain.provider.repository import (
    ProviderRepository,
    ProviderServiceRepository,
)
from app.infrastructure.services.package_version_service import PackageVersionService
from app.presentation.api.dependencies import (
    CurrentUser,
    get_adapter_registry,
    get_audit_service,
    get_current_user,
    get_db_session,
    get_provider_repository,
    get_provider_service,
    get_provider_service_repository,
    require_admin,
    require_super_admin,
    validate_organization_access,
)
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.adapters.registry import (
    AdapterNotFoundError,
    ServiceNotSupportedError,
)
from app.application.services.audit_service import AuditService
from app.domain.audit.models import AuditActorType
from app.presentation.api.models.provider import (
    CredentialCreate,
    CredentialRead,
    CredentialReadWithSecret,
    CredentialRevealResponse,
    CredentialRevealError,
    ProviderRead,
    ProviderServiceCreate as ProviderServiceCreateModel,
    ProviderServiceRead,
    ProviderServiceUpdate as ProviderServiceUpdateModel,
)
from app.infrastructure.errors import safe_error_message

router = APIRouter(tags=["Providers"])


@router.post("/", response_model=ProviderRead, status_code=status.HTTP_201_CREATED)
async def create_provider(
    provider_data: ProviderCreate,
    user: CurrentUser = Depends(require_super_admin),
    service: ProviderServiceClass = Depends(get_provider_service),
):
    """Requires SUPER_ADMIN role."""
    provider_data.created_by = UUID(user["id"])
    result = await service.create_provider(provider_data)
    return result


@router.get("/", response_model=List[ProviderRead])
async def list_providers(
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    user: CurrentUser = Depends(get_current_user),
    service: ProviderServiceClass = Depends(get_provider_service),
):
    """List providers with pagination.

    Non-super-admins only see active providers. Inactive (uninstalled)
    providers are a system-level concern that org admins and users cannot
    act on, so they are hidden from their view.
    """
    status_filter = None if user.get("role") == "super_admin" else ProviderStatus.ACTIVE
    return await service.list_providers(skip=skip, limit=limit, status=status_filter)


@router.get("/{provider_id}", response_model=ProviderRead)
async def get_provider(
    provider_id: UUID4 = Path(..., description="Provider ID"),
    user: CurrentUser = Depends(get_current_user),
    service: ProviderServiceClass = Depends(get_provider_service),
):
    """Get a provider by ID."""
    provider = await service.get_provider(provider_id)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider with ID {provider_id} not found",
        )
    return provider


@router.patch("/{provider_id}", response_model=ProviderRead)
async def update_provider(
    provider_update: ProviderUpdate,
    provider_id: UUID4 = Path(..., description="Provider ID"),
    user: CurrentUser = Depends(require_super_admin),
    service: ProviderServiceClass = Depends(get_provider_service),
):
    """Requires SUPER_ADMIN role."""
    try:
        return await service.update_provider(provider_id, provider_update)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: UUID4 = Path(..., description="Provider ID"),
    user: CurrentUser = Depends(require_super_admin),
    service: ProviderServiceClass = Depends(get_provider_service),
):
    """Requires SUPER_ADMIN role."""
    result = await service.delete_provider(provider_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider with ID {provider_id} not found",
        )


class ProviderPackageDefaults(BaseModel):
    """Original provider definition from the provider package."""

    name: str
    slug: str
    provider_type: str
    description: str | None = None
    endpoint_url: str | None = None
    config: Dict[str, Any] = {}
    capabilities: Dict[str, Any] = {}
    client_metadata: Dict[str, Any] = {}


@router.get("/{provider_id}/package-defaults", response_model=ProviderPackageDefaults)
async def get_provider_package_defaults(
    provider_id: UUID4 = Path(..., description="Provider ID"),
    user: CurrentUser = Depends(require_super_admin),
    service: ProviderServiceClass = Depends(get_provider_service),
    db: AsyncSession = Depends(get_db_session),
):
    """Original values from the installed package snapshot; useful for resetting to defaults. Requires SUPER_ADMIN."""
    provider = await service.get_provider(provider_id)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider with ID {provider_id} not found",
        )

    provider_slug = provider.client_metadata.get("slug")
    if not provider_slug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider slug not found in metadata. Provider may not have been installed from a package.",
        )

    package_version = await PackageVersionService.get_active_by_slug(
        db,
        PackageType.PROVIDER,
        provider_slug,
    )
    if not package_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Original provider definition not found. "
            f"No installed package snapshot for '{provider_slug}'.",
        )

    # Snapshot is the unified provider file content directly - no
    # {manifest, provider, adapter_config} envelope.
    provider_data = package_version.json_content

    client_metadata = {
        "credential_schema": provider_data.get("credential_schema"),
        "documentation_url": provider_data.get("documentation_url", ""),
        "icon_url": provider_data.get("icon_url", ""),
        "package_version": provider_data.get("version", "1.0.0"),
        "slug": provider_slug,
        "tier": provider_data.get("tier", "basic"),
        "category": provider_data.get("category", "core"),
        "credential_provider": provider_data.get("credential_provider"),
        "requires": provider_data.get("requires", []),
        "services_preview": provider_data.get("services_preview", []),
    }
    # Remove None values
    client_metadata = {k: v for k, v in client_metadata.items() if v is not None}

    return ProviderPackageDefaults(
        name=provider_data.get("name", provider_slug),
        slug=provider_slug,
        provider_type=provider_data.get("provider_type", "API"),
        description=provider_data.get("description"),
        endpoint_url=provider_data.get("base_url"),
        config={},
        capabilities={},
        client_metadata=client_metadata,
    )


@router.post(
    "/{provider_id}/credentials",
    response_model=Union[CredentialReadWithSecret, CredentialRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_credential(
    credential_data: CredentialCreate,
    provider_id: UUID4 = Path(..., description="Provider ID"),
    user: CurrentUser = Depends(require_admin),
    service: ProviderServiceClass = Depends(get_provider_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """
    Create a new credential for a provider.

    Requires ADMIN or SUPER_ADMIN role.

    For token-type credentials (oauth, oauth2, bearer, jwt, or custom with is_token_type=True),
    the secret_data is returned ONLY in this creation response. It cannot be retrieved later.
    """
    try:
        raw_org_id = user.get("org_id")
        if not raw_org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no associated organization",
            )
        organization_id = UUID(raw_org_id)
        await validate_organization_access(str(organization_id), user)

        # Get provider name for audit logging
        provider = await service.get_provider(provider_id)
        provider_name = provider.name if provider else str(provider_id)

        # Determine if this is a token type that can only be viewed once
        cred_type_lower = credential_data.credential_type.lower()
        is_token = cred_type_lower in ("oauth", "oauth2", "bearer", "jwt") or (
            cred_type_lower == "custom" and credential_data.is_token_type
        )

        command = ProviderCredentialCreate(
            provider_id=provider_id,
            organization_id=organization_id,
            created_by=UUID(user["id"]),
            name=credential_data.name,
            credential_type=CredentialType(credential_data.credential_type),
            credentials=credential_data.secret_data,
            expires_at=credential_data.expires_at,
            is_token_type=is_token,
        )

        created = await service.create_credential(command)

        # Audit log the credential creation
        await audit_service.log_credential_created(
            actor_id=UUID(user["id"]),
            actor_type=AuditActorType(user.get("role") or "user"),
            organization_id=organization_id,
            credential_id=created.id,
            credential_name=created.name,
            provider_name=provider_name,
            metadata={"credential_type": credential_data.credential_type},
        )

        # For token types, return the secret in the response (one-time view)
        if is_token:
            return CredentialReadWithSecret(
                id=created.id,
                provider_id=created.provider_id,
                name=created.name,
                credential_type=created.credential_type,
                is_active=created.is_active,
                is_token_type=True,
                expires_at=created.expires_at,
                created_at=created.created_at or datetime.now(timezone.utc),
                updated_at=created.updated_at or datetime.now(timezone.utc),
                secret_data=credential_data.secret_data,  # Return the original input
            )

        return created
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))


@router.get("/{provider_id}/credentials", response_model=List[CredentialRead])
async def list_credentials(
    provider_id: UUID4 = Path(..., description="Provider ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    user: CurrentUser = Depends(get_current_user),
    service: ProviderServiceClass = Depends(get_provider_service),
):
    """List credentials for a provider filtered by user's organization."""
    raw_org_id = user.get("org_id")
    if not raw_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no associated organization",
        )
    organization_id = UUID(raw_org_id)
    return await service.list_credentials_by_organization(
        organization_id=organization_id, provider_id=provider_id, skip=skip, limit=limit
    )


@router.get("/credentials/{credential_id}", response_model=CredentialRead)
async def get_credential(
    credential_id: UUID4 = Path(..., description="Credential ID"),
    user: CurrentUser = Depends(get_current_user),
    service: ProviderServiceClass = Depends(get_provider_service),
):
    """Get a credential by ID."""
    credential = await service.get_credential(credential_id)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential with ID {credential_id} not found",
        )
    await validate_organization_access(str(credential.organization_id), user)
    return credential


@router.patch("/credentials/{credential_id}", response_model=CredentialRead)
async def update_credential(
    credential_update: ProviderCredentialUpdate,
    credential_id: UUID4 = Path(..., description="Credential ID"),
    user: CurrentUser = Depends(require_admin),
    service: ProviderServiceClass = Depends(get_provider_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """
    Update a credential.

    Requires ADMIN or SUPER_ADMIN role.
    """
    try:
        credential = await service.get_credential(credential_id)
        if not credential:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Credential with ID {credential_id} not found",
            )
        await validate_organization_access(str(credential.organization_id), user)

        # Get provider name for audit logging
        provider = await service.get_provider(credential.provider_id)
        provider_name = provider.name if provider else str(credential.provider_id)

        updated = await service.update_credential(credential_id, credential_update)

        # Audit log the credential update
        await audit_service.log_credential_updated(
            actor_id=UUID(user["id"]),
            actor_type=AuditActorType(user.get("role") or "user"),
            organization_id=credential.organization_id,
            credential_id=credential_id,
            credential_name=credential.name,
            provider_name=provider_name,
        )

        return updated
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    credential_id: UUID4 = Path(..., description="Credential ID"),
    user: CurrentUser = Depends(require_admin),
    service: ProviderServiceClass = Depends(get_provider_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """
    Delete a credential.

    Requires ADMIN or SUPER_ADMIN role.
    """
    credential = await service.get_credential(credential_id)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential with ID {credential_id} not found",
        )
    await validate_organization_access(str(credential.organization_id), user)

    # Get provider name for audit logging before deletion
    provider = await service.get_provider(credential.provider_id)
    provider_name = provider.name if provider else str(credential.provider_id)
    credential_name = credential.name
    organization_id = credential.organization_id

    result = await service.delete_credential(credential_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential with ID {credential_id} not found",
        )

    # Audit log the credential deletion
    await audit_service.log_credential_deleted(
        actor_id=UUID(user["id"]),
        actor_type=AuditActorType(user.get("role") or "user"),
        organization_id=organization_id,
        credential_id=credential_id,
        credential_name=credential_name,
        provider_name=provider_name,
    )


# Token types that cannot be revealed after creation
_NON_REVEALABLE_TYPES = frozenset({"oauth", "oauth2", "bearer", "jwt"})

# Friendly messages for why credentials can't be revealed
_NON_REVEALABLE_REASONS = {
    "oauth": "OAuth tokens cannot be revealed after initial authorization. Re-authenticate to get new tokens.",
    "oauth2": "OAuth2 tokens cannot be revealed after initial authorization. Re-authenticate to get new tokens.",
    "bearer": "Bearer tokens can only be viewed at creation time.",
    "jwt": "JWT tokens can only be viewed when generated.",
    "custom_token": "This credential was marked as a one-time token and cannot be revealed.",
}


@router.get(
    "/credentials/{credential_id}/reveal",
    response_model=CredentialRevealResponse,
    responses={
        403: {
            "model": CredentialRevealError,
            "description": "Credential cannot be revealed",
        },
        404: {"description": "Credential not found"},
    },
)
async def reveal_credential_secret(
    credential_id: UUID4 = Path(..., description="Credential ID"),
    user: CurrentUser = Depends(require_admin),
    service: ProviderServiceClass = Depends(get_provider_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """
    Reveal the secret data for a credential.

    Requires ADMIN or SUPER_ADMIN role.

    Only certain credential types can be revealed:
    - api_key: Can be revealed (admin can view/regenerate in provider dashboard)
    - access_key: Can be revealed (same as api_key)
    - basic_auth: Can be revealed (you control these credentials)
    - custom: Can be revealed UNLESS is_token_type=True

    Token types that CANNOT be revealed (shown only at creation):
    - oauth / oauth2: Tokens from OAuth flow
    - bearer: One-time bearer tokens
    - jwt: Generated JWT tokens
    - custom with is_token_type=True: User marked as one-time token
    """
    logger = logging.getLogger(__name__)

    # Get credential (includes decrypted secret_data)
    credential = await service.get_credential_with_secret(credential_id)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential with ID {credential_id} not found",
        )

    # Validate organization access
    await validate_organization_access(str(credential.organization_id), user)

    # Check if credential type can be revealed (case-insensitive)
    cred_type_lower = credential.credential_type.lower()

    # Check if it's a non-revealable token type
    if cred_type_lower in _NON_REVEALABLE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "credential_not_viewable",
                "reason": _NON_REVEALABLE_REASONS.get(
                    cred_type_lower, "This credential type cannot be revealed."
                ),
                "credential_type": credential.credential_type,
            },
        )

    # Check if custom type was marked as token
    if cred_type_lower == "custom" and getattr(credential, "is_token_type", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "credential_not_viewable",
                "reason": _NON_REVEALABLE_REASONS["custom_token"],
                "credential_type": credential.credential_type,
            },
        )

    # Get provider name for audit logging
    provider = await service.get_provider(credential.provider_id)
    provider_name = provider.name if provider else str(credential.provider_id)

    # Audit log the reveal action (CRITICAL severity - sensitive data access)
    from app.domain.audit.models import (
        AuditAction,
        AuditSeverity,
        AuditCategory,
        ResourceType,
    )

    await audit_service.log_event(
        actor_id=UUID(user["id"]),
        actor_type=AuditActorType(user.get("role") or "user"),
        action=AuditAction.REVEAL,
        resource_type=ResourceType.CREDENTIAL,
        resource_id=credential_id,
        resource_name=credential.name,
        organization_id=credential.organization_id,
        severity=AuditSeverity.CRITICAL,
        category=AuditCategory.SECURITY,
        metadata={
            "credential_type": credential.credential_type,
            "provider_name": provider_name,
        },
    )

    # Also log to application logger
    logger.info(
        "Credential secret revealed",
        extra={
            "credential_id": str(credential_id),
            "credential_name": credential.name,
            "credential_type": credential.credential_type,
            "revealed_by_user_id": user["id"],
            "revealed_by_username": user.get("username", "unknown"),
            "organization_id": str(credential.organization_id),
        },
    )

    return CredentialRevealResponse(
        secret_data=credential.credentials,
        revealed_at=datetime.now(timezone.utc),
        credential_id=credential_id,
        credential_type=credential.credential_type,
    )


@router.post(
    "/{provider_id}/services",
    response_model=ProviderServiceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider_service(
    service_data: ProviderServiceCreateModel,
    provider_id: UUID4 = Path(..., description="Provider ID"),
    user: CurrentUser = Depends(require_super_admin),
    service: ProviderServiceClass = Depends(get_provider_service),
):
    """Create a new service for a provider. Requires SUPER_ADMIN role."""
    try:
        if not service_data.service_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="service_type is required",
            )

        command = ProviderServiceCreate(
            provider_id=provider_id,
            service_id=service_data.service_id,
            display_name=service_data.display_name,
            service_type=service_data.service_type,
            description=service_data.description,
            endpoint=service_data.endpoint,
            parameter_schema=service_data.parameter_schema,
            result_schema=service_data.result_schema,
            example_parameters=service_data.example_parameters,
            client_metadata={},
            created_by=UUID(user["id"]),
        )

        return await service.create_provider_service(command)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))


@router.get("/{provider_id}/services", response_model=List[ProviderServiceRead])
async def list_provider_services(
    provider_id: UUID4 = Path(..., description="Provider ID"),
    user: CurrentUser = Depends(get_current_user),
    service: ProviderServiceClass = Depends(get_provider_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
):
    """List services for a provider."""
    return await service.list_provider_services(
        provider_id=provider_id, skip=skip, limit=limit
    )


@router.get("/services/{service_id}", response_model=ProviderServiceRead)
async def get_provider_service_endpoint(
    service_id: str = Path(
        ...,
        description="Service ID (UUID or service_id string like 'myprovider.my_service')",
    ),
    user: CurrentUser = Depends(get_current_user),
    service: ProviderServiceClass = Depends(get_provider_service),
    service_repo: ProviderServiceRepository = Depends(get_provider_service_repository),
):
    """Get a provider service by ID (supports both UUID and service_id string)."""
    try:
        # Try parsing as UUID first
        try:
            service_uuid = UUID(service_id)
            provider_service = await service.get_provider_service(service_uuid)
            return provider_service
        except ValueError:
            # Not a UUID - try looking up by service_id string (e.g., "myprovider.my_service")
            provider_service = await service_repo.get_by_service_id(
                service_id, skip=0, limit=1
            )
            if not provider_service:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Provider service with service_id '{service_id}' not found",
                )
            return provider_service
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))


@router.patch("/services/{service_id}", response_model=ProviderServiceRead)
async def update_provider_service(
    service_update: ProviderServiceUpdateModel,
    service_id: UUID4 = Path(..., description="Service ID"),
    user: CurrentUser = Depends(require_super_admin),
    service: ProviderServiceClass = Depends(get_provider_service),
):
    """Update a provider service. Requires SUPER_ADMIN role."""
    try:
        # Convert presentation model to DTO
        update_dto = ProviderServiceUpdate(
            display_name=service_update.display_name,
            description=service_update.description,
            endpoint=service_update.endpoint,
            parameter_schema=service_update.parameter_schema,
            result_schema=service_update.result_schema,
            example_parameters=service_update.example_parameters,
            is_active=service_update.is_active,
            client_metadata=service_update.client_metadata,
        )
        return await service.update_provider_service(service_id, update_dto)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))


@router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider_service(
    service_id: UUID4 = Path(..., description="Service ID"),
    user: CurrentUser = Depends(require_super_admin),
    service: ProviderServiceClass = Depends(get_provider_service),
):
    """Delete a provider service. Requires SUPER_ADMIN role."""
    result = await service.delete_provider_service(service_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider service with ID {service_id} not found",
        )


class ServicePackageDefaults(BaseModel):
    """Original service definition from the provider package."""

    display_name: str
    description: str | None = None
    endpoint: str | None = None
    parameter_schema: Dict[str, Any] = {}
    result_schema: Dict[str, Any] = {}
    example_parameters: Dict[str, Any] = {}
    client_metadata: Dict[str, Any] = {}


@router.get(
    "/services/{service_id}/package-defaults", response_model=ServicePackageDefaults
)
async def get_service_package_defaults(
    service_id: UUID4 = Path(..., description="Service ID"),
    user: CurrentUser = Depends(require_super_admin),
    service: ProviderServiceClass = Depends(get_provider_service),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get the original service definition from the installed package snapshot.

    Reads the pre-edit service data from package_versions.json_content (written
    by the installer at install time). Handles both Pattern A (services embedded
    in adapter-config.json) and Pattern B (split services/*.json) layouts.

    Requires SUPER_ADMIN role.
    """
    try:
        # Get the service to find its service_id string (e.g., "myprovider.my_service")
        provider_service = await service.get_provider_service(service_id)

        # Get the provider to find its slug
        provider = await provider_repo.get_by_id(provider_service.provider_id)
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Provider not found for service",
            )

        # Parse the service_id string (e.g., "myprovider.my_service" -> "my_service")
        service_id_str = provider_service.service_id
        if "." in service_id_str:
            service_slug = service_id_str.split(".")[-1]
        else:
            service_slug = service_id_str

        provider_slug = provider.slug

        # Load the installed package snapshot from the DB
        package_version = await PackageVersionService.get_active_by_slug(
            db,
            PackageType.PROVIDER,
            provider_slug,
        )
        if not package_version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Original service definition not found. "
                f"No installed package snapshot for '{provider_slug}'.",
            )

        content = package_version.json_content
        # Pattern B: split services stored by slug in json_content["services"]
        service_data = content.get("services", {}).get(service_slug)

        # Pattern A: services embedded in adapter_config
        if service_data is None:
            service_data = (
                content.get("adapter_config", {}).get("services", {}).get(service_slug)
            )

        if not service_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Original service definition not found in package. "
                f"Service '{service_slug}' not present in package '{provider_slug}'.",
            )

        # Build client_metadata from the various fields in the package
        client_metadata = {
            "method": service_data.get("method", "POST"),
            "requires_credentials": service_data.get("requires_credentials", True),
            "post_processing": service_data.get("post_processing"),
            "polling": service_data.get("polling"),
            "ui_hints": service_data.get("ui_hints"),
        }
        # Remove None values
        client_metadata = {k: v for k, v in client_metadata.items() if v is not None}

        return ServicePackageDefaults(
            display_name=service_data.get("display_name", service_slug),
            description=service_data.get("description"),
            endpoint=service_data.get("endpoint"),
            parameter_schema=service_data.get("parameter_schema", {}),
            result_schema=service_data.get("result_schema", {}),
            example_parameters=service_data.get("example_parameters", {}),
            client_metadata=client_metadata,
        )

    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))


class ServiceTestRequest(BaseModel):
    """Request body for testing a provider service."""

    parameters: Dict[str, Any] = {}


class FieldOption(BaseModel):
    """A single option for a dynamic field."""

    value: str
    label: str
    metadata: Dict[str, Any] = {}


class FieldOptionsResponse(BaseModel):
    """Response containing field options."""

    options: List[FieldOption]
    has_more: bool = False
    offset: str | None = None


class FieldOptionsRequest(BaseModel):
    """Request body for fetching field options."""

    parameters: Dict[str, Any] = {}


@router.post("/{provider_id}/field-options")
async def get_field_options(
    request_body: FieldOptionsRequest,
    provider_id: UUID4 = Path(..., description="Provider ID"),
    credential_id: UUID4 = Query(..., description="Credential ID to use for API calls"),
    service: str = Query(..., description="Metadata service ID (e.g., 'list_items')"),
    options_path: str = Query(
        ..., description="JSONPath to the options array (e.g., 'bases')"
    ),
    value_field: str = Query(
        ..., description="Field name for the option value (e.g., 'id')"
    ),
    label_field: str = Query(
        ..., description="Field name for the option label (e.g., 'name')"
    ),
    user: CurrentUser = Depends(get_current_user),
    provider_service: ProviderServiceClass = Depends(get_provider_service),
):
    """
    Fetch dynamic field options by executing a provider's metadata service.

    This is a generic endpoint that can fetch options for any provider that exposes
    metadata services. For example, providers can expose services to list workspaces,
    databases, channels, or other resources that populate dropdown fields.
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        raw_org_id = user.get("org_id")
        if not raw_org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no associated organization",
            )
        organization_id = UUID(raw_org_id)

        # Validate credential access
        credential = await provider_service.get_credential_with_secret(credential_id)
        if not credential:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Credential with ID {credential_id} not found",
            )
        await validate_organization_access(str(credential.organization_id), user)

        # Get the provider
        provider = await provider_service.get_provider(provider_id)
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider with ID {provider_id} not found",
            )

        # Build full service_id (e.g., "myprovider.list_items")
        service_id_str = f"{provider.slug}.{service}"

        # Look up the service to get endpoint/method from client_metadata
        service_record = await provider_service.get_provider_service_by_service_id(
            provider_id=provider_id,
            service_id_str=service_id_str,
        )
        if not service_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service '{service_id_str}' not found",
            )

        # Extract service config from client_metadata
        service_config = None
        if service_record.client_metadata:
            service_config = {
                "endpoint": service_record.client_metadata.get("endpoint", "/"),
                "method": service_record.client_metadata.get("method", "POST"),
            }

        # Get adapter from registry
        registry = get_adapter_registry()
        try:
            adapter = registry.get_adapter_for_service(service_id_str)
        except ServiceNotSupportedError:
            try:
                adapter = registry.get_adapter_by_name(provider.name)
            except AdapterNotFoundError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No adapter found for service '{service_id_str}'",
                )

        # Execute the metadata service with service config
        result = await adapter.execute_service(
            service_id=service_id_str,
            parameters=request_body.parameters,
            credentials=credential.credentials,
            organization_id=organization_id,
            service_config=service_config,
        )

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Metadata service failed: {result.error}",
            )

        # Extract options from the result using the options_path
        # Uses extract_list utility which supports:
        # - Simple paths: "bases", "tables"
        # - Array filtering: "tables[name=${table_id}].views" or "tables[name=${table_id}].fields"
        #   where ${param_name} is replaced with value from request parameters
        from app.infrastructure.utils import extract_list

        # Defensive: treat "undefined", "null", None as empty path (return full response)
        safe_options_path = (
            options_path if options_path not in ("undefined", "null", None) else ""
        )
        data = extract_list(result.data, safe_options_path, request_body.parameters)

        # Build options list
        options = []
        for item in data:
            if isinstance(item, dict):
                value = str(item.get(value_field, ""))
                label = str(item.get(label_field, value))
                # Include all fields as metadata for potential future use
                options.append(
                    FieldOption(
                        value=value,
                        label=label,
                        metadata=item,
                    )
                )

        # Check for pagination offset in result (only if result is a dict)
        has_more = False
        offset = None
        if isinstance(result.data, dict):
            offset = result.data.get("offset")
            has_more = offset is not None

        return FieldOptionsResponse(
            options=options,
            has_more=has_more,
            offset=offset,
        )

    except Exception as e:
        logger.exception(f"Error fetching field options: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch field options",
        )


# --- Table Schema Endpoint for Schema-Driven Forms ---


class TableSchemaField(BaseModel):
    """A field definition from a table schema with generic types."""

    name: str
    type: str  # Generic type: text, textarea, number, select, multiselect, checkbox, date, datetime, array, reference, computed
    description: str | None = None
    options: Dict[str, Any] = {}
    is_computed: bool = False


class TableSchemaResponse(BaseModel):
    """Response containing table schema fields with generic types."""

    table_name: str
    fields: List[TableSchemaField]


class TableSchemaRequest(BaseModel):
    """Request body for fetching table schema."""

    parameters: Dict[str, Any] = {}


async def _load_provider_snapshot(
    db: AsyncSession, provider_slug: str
) -> Dict[str, Any]:
    """Load the unified provider snapshot from the active package version.

    Snapshot is the full unified provider file content, not wrapped under
    {manifest, provider, adapter_config} keys. Callers read fields like
    field_type_mapping directly off the returned dict.
    """
    package_version = await PackageVersionService.get_active_by_slug(
        db,
        PackageType.PROVIDER,
        provider_slug,
    )
    if not package_version:
        return {}
    return package_version.json_content or {}


def _map_field_type(provider_type: str, field_type_mapping: Dict[str, str]) -> str:
    """Map a provider-specific field type to a generic type."""
    # If we have a mapping, use it
    if provider_type in field_type_mapping:
        return field_type_mapping[provider_type]

    # Default fallback to text for unknown types
    return "text"


@router.post("/{provider_id}/table-schema")
async def get_table_schema(
    request_body: TableSchemaRequest,
    provider_id: UUID4 = Path(..., description="Provider ID"),
    credential_id: UUID4 = Query(..., description="Credential ID to use for API calls"),
    schema_service: str = Query(
        ..., description="The schema service to call (e.g., 'get_table_schema')"
    ),
    table_param: str = Query(
        ...,
        description="Parameter name containing the table identifier (e.g., 'table_id')",
    ),
    user: CurrentUser = Depends(get_current_user),
    provider_service: ProviderServiceClass = Depends(get_provider_service),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Fetch table schema for any provider that supports schema services.

    This is a generic endpoint that works with any provider by:
    1. Loading the field_type_mapping from the provider's snapshot
    2. Calling the specified schema service
    3. Mapping provider-specific field types to generic types

    Generic field types returned:
    - text: Single line text inputs
    - textarea: Multi-line text
    - number: Numeric values
    - select: Single selection from options
    - multiselect: Multiple selection from options
    - checkbox: Boolean toggle
    - date: Date picker
    - datetime: Date and time picker
    - array: List of values (attachments, etc.)
    - reference: Links to other records
    - computed: Read-only calculated fields

    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        raw_org_id = user.get("org_id")
        if not raw_org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no associated organization",
            )
        organization_id = UUID(raw_org_id)

        # Validate credential access
        credential = await provider_service.get_credential_with_secret(credential_id)
        if not credential:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Credential with ID {credential_id} not found",
            )
        await validate_organization_access(str(credential.organization_id), user)

        # Get the provider
        provider = await provider_service.get_provider(provider_id)
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider with ID {provider_id} not found",
            )

        # Validate provider slug to prevent path traversal
        validate_safe_slug(provider.slug, "provider_slug")

        # Load provider snapshot to get field_type_mapping
        snapshot = await _load_provider_snapshot(db, provider.slug)
        field_type_mapping = snapshot.get("field_type_mapping", {})

        # Build service ID
        service_id_str = f"{provider.slug}.{schema_service}"

        # Look up the service to get endpoint/method from client_metadata
        service_record = await provider_service.get_provider_service_by_service_id(
            provider_id=provider_id,
            service_id_str=service_id_str,
        )
        if not service_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service '{service_id_str}' not found",
            )

        # Extract service config from client_metadata
        service_config = None
        if service_record.client_metadata:
            service_config = {
                "endpoint": service_record.client_metadata.get("endpoint", "/"),
                "method": service_record.client_metadata.get("method", "GET"),
            }

        # Get adapter from registry
        registry = get_adapter_registry()
        try:
            adapter = registry.get_adapter_for_service(service_id_str)
        except ServiceNotSupportedError:
            try:
                adapter = registry.get_adapter_by_name(provider.name)
            except AdapterNotFoundError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No adapter found for service '{service_id_str}'",
                )

        # Execute the schema service with provided parameters
        result = await adapter.execute_service(
            service_id=service_id_str,
            parameters=request_body.parameters,
            credentials=credential.credentials,
            organization_id=organization_id,
            service_config=service_config,
        )

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Schema service failed: {result.error}",
            )

        # Get the table identifier from parameters
        table_id = request_body.parameters.get(table_param)
        if not table_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Required parameter '{table_param}' not provided",
            )

        # Find the requested table in the response
        tables = result.data.get("tables", [])
        target_table = None
        for table in tables:
            # Match by name or ID
            if table.get("name") == table_id or table.get("id") == table_id:
                target_table = table
                break

        if not target_table:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Table '{table_id}' not found",
            )

        # Extract and normalize fields using field_type_mapping
        schema_fields = []
        for field in target_table.get("fields", []):
            provider_field_type = field.get("type", "text")
            generic_type = _map_field_type(provider_field_type, field_type_mapping)

            schema_fields.append(
                TableSchemaField(
                    name=field.get("name", ""),
                    type=generic_type,
                    description=field.get("description"),
                    options=field.get("options", {}),
                    is_computed=generic_type == "computed",
                )
            )

        return TableSchemaResponse(
            table_name=target_table.get("name", table_id),
            fields=schema_fields,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching table schema: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch table schema",
        )


@router.post("/{provider_id}/services/{service_id}/test")
async def test_provider_service(
    request_body: ServiceTestRequest,
    provider_id: UUID4 = Path(..., description="Provider ID"),
    service_id: str = Path(
        ...,
        description="Service ID (database UUID or service_id string like 'myprovider.my_service')",
    ),
    user: CurrentUser = Depends(get_current_user),
    service: ProviderServiceClass = Depends(get_provider_service),
):
    """
    Test a provider service with given parameters.

    Uses the user's credentials for the provider and executes the service
    with the provided parameters to test the configuration.

    Args:
        provider_id: Provider UUID
        service_id: Provider service UUID OR service_id string (e.g., "myprovider.my_service")
        parameters: Service parameters to test with

    Returns:
        Service execution result
    """
    try:
        raw_org_id = user.get("org_id")
        if not raw_org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no associated organization",
            )
        organization_id = UUID(raw_org_id)

        # Get the provider
        provider = await service.get_provider(provider_id)
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider with ID {provider_id} not found",
            )

        # Get the service configuration - try as UUID first, then as service_id string
        provider_svc = None
        try:
            # Try parsing as UUID
            service_uuid = UUID(service_id)
            provider_svc = await service.get_provider_service(service_uuid)
        except (ValueError, TypeError):
            # Not a UUID, try looking up by service_id string
            pass

        if provider_svc is None:
            # Look up by service_id string
            provider_svc = await service.get_provider_service_by_service_id(
                provider_id, service_id
            )

        # Get the user's credentials for this provider
        credentials_list = await service.list_credentials_by_organization(
            organization_id=organization_id, provider_id=provider_id, skip=0, limit=1
        )

        if not credentials_list:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No credentials found for provider '{provider.name}'. Please add credentials first.",
            )

        # Get the full credential with secret data
        credential = await service.get_credential_with_secret(credentials_list[0].id)
        if not credential:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No credentials found for provider '{provider.name}'. Please add credentials first.",
            )

        # Get the adapter registry
        registry = get_adapter_registry()

        if not provider_svc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service '{service_id}' not found for provider",
            )

        # Get adapter for this service
        service_id_str = provider_svc.service_id  # e.g., "myprovider.my_service"

        try:
            adapter = registry.get_adapter_for_service(service_id_str)
        except ServiceNotSupportedError:
            # Fall back to getting adapter by provider name
            try:
                adapter = registry.get_adapter_by_name(provider.name)
            except AdapterNotFoundError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No adapter found for service '{service_id_str}' or provider '{provider.name}'",
                )

        # Extract service config from client_metadata for endpoint/method
        service_config = None
        if provider_svc.client_metadata:
            service_config = {
                "endpoint": provider_svc.client_metadata.get("endpoint", "/"),
                "method": provider_svc.client_metadata.get("method", "POST"),
            }

        # Execute the service
        result = await adapter.execute_service(
            service_id=service_id_str,
            parameters=request_body.parameters,
            credentials=credential.credentials,  # Decrypted credentials
            organization_id=organization_id,
            service_config=service_config,
        )

        if result.success:
            return {
                "success": True,
                "data": result.data,
                "execution_time_ms": result.execution_time_ms,
                "metadata": result.metadata,
            }
        else:
            return {
                "success": False,
                "error": result.error,
                "execution_time_ms": result.execution_time_ms,
                "metadata": result.metadata,
            }

    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))
    except Exception as e:
        logger.exception(f"Error testing service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service test failed",
        )
