# api/app/presentation/api/organization_secrets.py

"""Organization secret management.

SECURITY:
- LIST returns names/metadata only - never secret_data.
- GET (single) decrypts secret_data; rate-limit & audit at caller.
- Names are immutable post-create.
- Never log secret_data or template context.
"""

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field, UUID4
from app.infrastructure.repositories.organization_secret_repository import (
    OrganizationSecret,
)
from app.domain.organization_secret.repository import OrganizationSecretRepository
from app.application.services.audit_service import AuditService
from app.domain.audit.models import AuditActorType
from app.presentation.api.dependencies import (
    CurrentUser,
    get_audit_service,
    get_current_user,
    get_organization_secret_repository,
    require_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Organization Secrets"])


def parse_token_with_expiration(token_value: str) -> Tuple[str, Optional[datetime]]:
    """Strip optional -YYYYMMDD suffix → (token, expires_at). Example: github_pat_xxx-20260115."""
    pattern = r"^(.+)-(\d{8})$"
    match = re.match(pattern, token_value)

    if match:
        actual_token = match.group(1)
        date_str = match.group(2)
        try:
            expires_at = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=UTC)
            logger.info(f"Parsed expiration date from token: {expires_at.date()}")
            return actual_token, expires_at
        except ValueError:
            logger.warning(f"Invalid date format in token suffix: {date_str}")
            return token_value, None

    return token_value, None


class SecretCreate(BaseModel):
    name: str = Field(
        ..., min_length=1, max_length=255, description="Secret name (immutable)"
    )
    secret_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Secret type (bearer, api_key, custom)",
    )
    secret_data: dict[str, Any] = Field(
        ..., description="Secret data as JSON (will be encrypted)"
    )
    is_active: bool = Field(True, description="Whether the secret is active on creation")
    expires_at: str | None = Field(None, description="ISO8601 expiration date")


class SecretUpdate(BaseModel):
    secret_data: dict[str, Any] | None = Field(
        None, description="New secret data (will be encrypted)"
    )
    is_active: bool | None = Field(None, description="Active status")
    expires_at: str | None = Field(None, description="ISO8601 expiration date")


class SecretMetadata(BaseModel):
    """Response model for secret metadata (NO secret_data)."""

    id: str
    name: str
    secret_type: str
    description: str | None = None
    is_active: bool
    is_protected: bool = False
    expires_at: str | None
    created_at: str
    updated_at: str


class SecretRead(SecretMetadata):
    """Single-secret response - includes decrypted secret_data."""

    secret_data: dict[str, Any]  # SECURITY: only exposed in single-secret GET


@router.get("/secrets", response_model=List[SecretMetadata])
async def list_secrets(
    user: CurrentUser = Depends(get_current_user),
    repo: OrganizationSecretRepository = Depends(get_organization_secret_repository),
):
    """Metadata-only listing. Protected secrets (e.g. ENTITLEMENT_TOKEN) are super_admin-only."""
    try:
        org_id = user.get("org_id") or user.get("organization_id")
        user_role = user.get("role", "user")
        logger.info(
            f"List secrets request - User org_id: {org_id}, User: {user.get('email')}, Role: {user_role}"
        )
        if not org_id:
            logger.warning("User has no organization_id, returning empty list")
            return []

        secrets = await repo.list_metadata_only(
            organization_id=uuid.UUID(org_id),
            active_only=False,
        )

        if user_role != "super_admin":
            secrets = [s for s in secrets if not s.get("is_protected", False)]

        logger.info(f"Found {len(secrets)} secrets for org {org_id}")
        return secrets
    except Exception as e:
        logger.error(f"Failed to list secrets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list secrets",
        )


@router.get("/secrets/{secret_id}", response_model=SecretRead)
async def get_secret(
    secret_id: UUID4 = Path(..., description="Secret ID"),
    user: CurrentUser = Depends(get_current_user),
    repo: OrganizationSecretRepository = Depends(get_organization_secret_repository),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Returns DECRYPTED secret_data. Logs a secret_revealed audit event. Protected secrets are super_admin-only."""
    try:
        org_id = user.get("org_id") or user.get("organization_id")
        user_role = user.get("role", "user")
        if not org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User does not belong to an organization",
            )

        secret = await repo.get_by_id(
            secret_id=uuid.UUID(str(secret_id)),
            organization_id=uuid.UUID(org_id),
        )

        if not secret:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Secret {secret_id} not found",
            )

        if secret.is_protected and user_role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This secret is protected and can only be accessed by super admins",
            )

        # AUDIT: secret_data was decrypted and returned - must be logged
        try:
            await audit_service.log_secret_revealed(
                actor_id=uuid.UUID(user["id"]),
                actor_type=AuditActorType(user_role or "user"),
                organization_id=uuid.UUID(org_id),
                secret_id=secret.id,
                secret_name=secret.name,
            )
        except Exception as audit_error:
            logger.warning(f"Failed to log secret reveal audit event: {audit_error}")

        return SecretRead(
            id=str(secret.id),
            name=secret.name,
            secret_type=secret.secret_type,
            description=secret.description,
            secret_data=secret.secret_data,
            is_active=secret.is_active,
            is_protected=secret.is_protected,
            expires_at=secret.expires_at.isoformat() if secret.expires_at else None,
            created_at=secret.created_at.isoformat() if secret.created_at else "",
            updated_at=secret.updated_at.isoformat() if secret.updated_at else "",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get secret {secret_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get secret",
        )


@router.post(
    "/secrets", response_model=SecretMetadata, status_code=status.HTTP_201_CREATED
)
async def create_secret(
    data: SecretCreate,
    user: CurrentUser = Depends(require_admin),
    repo: OrganizationSecretRepository = Depends(get_organization_secret_repository),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Admin only. Encrypts secret_data at rest; name is immutable post-create."""
    try:
        org_id = user.get("org_id") or user.get("organization_id")
        if not org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User does not belong to an organization",
            )

        existing = await repo.get_by_name(
            name=data.name,
            organization_id=uuid.UUID(org_id),
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Secret with name '{data.name}' already exists",
            )

        expires_at = None
        if data.expires_at:
            expires_at = datetime.fromisoformat(data.expires_at.replace("Z", "+00:00"))

        # ENTITLEMENT_TOKEN may carry expiration in its suffix; parsed value wins over caller's expires_at
        secret_data = data.secret_data
        if data.name == "ENTITLEMENT_TOKEN":
            token_value = secret_data.get("token") or secret_data.get("api_key")
            if token_value:
                actual_token, parsed_expires = parse_token_with_expiration(token_value)
                if parsed_expires:
                    expires_at = parsed_expires
                    if "token" in secret_data:
                        secret_data = {**secret_data, "token": actual_token}
                    else:
                        secret_data = {**secret_data, "api_key": actual_token}

        secret = OrganizationSecret(
            id=uuid.uuid4(),
            organization_id=uuid.UUID(org_id),
            name=data.name,
            secret_type=data.secret_type,
            secret_data=secret_data,
            is_active=data.is_active,
            expires_at=expires_at,
            created_by=uuid.UUID(user["id"]),
        )

        created = await repo.create(secret)

        # AUDIT: never log actual value
        try:
            user_role = user.get("role", "admin")
            await audit_service.log_secret_created(
                actor_id=uuid.UUID(user["id"]),
                actor_type=AuditActorType(user_role or "admin"),
                organization_id=uuid.UUID(org_id),
                secret_id=created.id,
                secret_name=created.name,
                metadata={"secret_type": created.secret_type},
            )
        except Exception as audit_error:
            logger.warning(f"Failed to log secret creation audit event: {audit_error}")

        # Return metadata only (no secret_data)
        return SecretMetadata(
            id=str(created.id),
            name=created.name,
            secret_type=created.secret_type,
            is_active=created.is_active,
            expires_at=created.expires_at.isoformat() if created.expires_at else None,
            created_at=created.created_at.isoformat() if created.created_at else "",
            updated_at=created.updated_at.isoformat() if created.updated_at else "",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create secret: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create secret",
        )


@router.put("/secrets/{secret_id}", response_model=SecretMetadata)
async def update_secret(
    secret_id: UUID4 = Path(..., description="Secret ID"),
    data: SecretUpdate = SecretUpdate(),  # type: ignore[call-arg]  - SecretUpdate Pydantic model default instance; pyright cannot infer dynamic Pydantic __init__ kwargs
    user: CurrentUser = Depends(require_admin),
    repo: OrganizationSecretRepository = Depends(get_organization_secret_repository),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Admin only. Name is immutable; only secret_data, is_active, expires_at update."""
    try:
        org_id = user.get("org_id") or user.get("organization_id")
        if not org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User does not belong to an organization",
            )

        secret = await repo.get_by_id(
            secret_id=uuid.UUID(str(secret_id)),
            organization_id=uuid.UUID(org_id),
        )

        if not secret:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Secret {secret_id} not found",
            )

        expires_at = secret.expires_at
        if data.expires_at is not None:
            expires_at = datetime.fromisoformat(data.expires_at.replace("Z", "+00:00"))

        # secret_data optional → toggling is_active doesn't require re-sending the secret
        secret_data = data.secret_data
        if secret_data is not None:
            if secret.name == "ENTITLEMENT_TOKEN":
                token_value = secret_data.get("token") or secret_data.get("api_key")
                if token_value:
                    actual_token, parsed_expires = parse_token_with_expiration(
                        token_value
                    )
                    if parsed_expires:
                        expires_at = parsed_expires
                        if "token" in secret_data:
                            secret_data = {**secret_data, "token": actual_token}
                        else:
                            secret_data = {**secret_data, "api_key": actual_token}
            secret.secret_data = secret_data

        secret.is_active = (
            data.is_active if data.is_active is not None else secret.is_active
        )
        secret.expires_at = expires_at

        updated = await repo.update(secret)

        # AUDIT: never log values
        try:
            user_role = user.get("role", "admin")
            await audit_service.log_secret_updated(
                actor_id=uuid.UUID(user["id"]),
                actor_type=AuditActorType(user_role or "admin"),
                organization_id=uuid.UUID(org_id),
                secret_id=updated.id,
                secret_name=updated.name,
            )
        except Exception as audit_error:
            logger.warning(f"Failed to log secret update audit event: {audit_error}")

        return SecretMetadata(
            id=str(updated.id),
            name=updated.name,
            secret_type=updated.secret_type,
            is_active=updated.is_active,
            expires_at=updated.expires_at.isoformat() if updated.expires_at else None,
            created_at=updated.created_at.isoformat() if updated.created_at else "",
            updated_at=updated.updated_at.isoformat() if updated.updated_at else "",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update secret {secret_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update secret",
        )


@router.delete("/secrets/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret(
    secret_id: UUID4 = Path(..., description="Secret ID"),
    user: CurrentUser = Depends(require_admin),
    repo: OrganizationSecretRepository = Depends(get_organization_secret_repository),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Admin only. Protected secrets return 403."""
    try:
        org_id = user.get("org_id") or user.get("organization_id")
        if not org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User does not belong to an organization",
            )

        # Capture name before deletion for audit
        secret = await repo.get_by_id(
            secret_id=uuid.UUID(str(secret_id)),
            organization_id=uuid.UUID(org_id),
        )
        secret_name = secret.name if secret else f"Secret {secret_id}"

        deleted = await repo.delete(
            secret_id=uuid.UUID(str(secret_id)),
            organization_id=uuid.UUID(org_id),
        )

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Secret {secret_id} not found",
            )

        try:
            user_role = user.get("role", "admin")
            await audit_service.log_secret_deleted(
                actor_id=uuid.UUID(user["id"]),
                actor_type=AuditActorType(user_role or "admin"),
                organization_id=uuid.UUID(org_id),
                secret_id=uuid.UUID(str(secret_id)),
                secret_name=secret_name,
            )
        except Exception as audit_error:
            logger.warning(f"Failed to log secret deletion audit event: {audit_error}")

        return None
    except ValueError as e:
        # Repo raises ValueError when secret is protected
        logger.error(f"Failed to delete secret {secret_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Protected secret cannot be deleted",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete secret {secret_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete secret",
        )
