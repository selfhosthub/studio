# api/app/presentation/api/users.py

"""User-specific operations: avatar upload/delete."""

import logging
import hashlib
import uuid
from pathlib import Path
from typing import Dict

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from PIL import Image
import io

from app.application.dtos import UserUpdate
from app.application.interfaces.service_interfaces import OrganizationServiceInterface
from app.config.settings import settings
from app.application.services.audit_service import AuditService
from app.domain.audit.models import (
    AuditAction,
    AuditActorType,
    AuditCategory,
    AuditSeverity,
    AuditStatus,
    ResourceType,
)
from app.domain.common.exceptions import EntityNotFoundError
from app.presentation.api.dependencies import (
    get_audit_service,
    get_current_user,
    get_organization_service,
)

logger = logging.getLogger(__name__)

CurrentUser = dict

router = APIRouter()

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
MAX_FILE_SIZE = settings.AVATAR_MAX_FILE_SIZE
AVATAR_SIZE = (500, 500)


def get_workspace_path() -> Path:
    workspace = settings.WORKSPACE_ROOT
    if not workspace:
        raise RuntimeError("WORKSPACE_ROOT environment variable is not set")
    return Path(workspace)


def validate_image(file: UploadFile) -> None:
    """400 on missing/disallowed extension or non-image content type."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required"
        )

    ext = file.filename.split(".")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image"
        )


async def process_avatar(file: UploadFile) -> bytes:
    """Decode, flatten alpha onto white, resize, JPEG-encode. 400 on size/decode failure."""
    try:
        content = await file.read()

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE / (1024*1024)}MB",
            )

        image = Image.open(io.BytesIO(content))

        if image.mode == "RGBA":
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])  # alpha channel
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        image.thumbnail(AVATAR_SIZE, Image.Resampling.LANCZOS)

        output = io.BytesIO()
        image.save(output, format="JPEG", quality=85, optimize=True)
        return output.getvalue()

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to process avatar image")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to process image",
        )


@router.post("/users/{user_id}/avatar", response_model=Dict[str, str])
async def upload_user_avatar(
    request: Request,
    user_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    org_service: OrganizationServiceInterface = Depends(get_organization_service),
    audit_service: AuditService = Depends(get_audit_service),
) -> Dict[str, str]:
    """Self-only unless admin. 403 otherwise. Returns {'avatar_url': ...}."""
    ip_address = request.client.host if request.client else None
    actor_id = uuid.UUID(current_user["id"])
    org_id = uuid.UUID(current_user["org_id"]) if current_user.get("org_id") else None

    async def _audit(
        action,
        *,
        status_val: AuditStatus = AuditStatus.SUCCESS,
        error_msg=None,
        meta=None,
    ):
        try:
            await audit_service.log_event(
                actor_id=actor_id,
                actor_type=AuditActorType(current_user.get("role", "user")),
                action=action,
                resource_type=ResourceType.USER,
                resource_id=user_id,
                resource_name="avatar",
                organization_id=org_id,
                severity=(
                    AuditSeverity.WARNING
                    if status_val == AuditStatus.FAILED
                    else AuditSeverity.INFO
                ),
                category=AuditCategory.SECURITY,
                status=status_val,
                error_message=error_msg,
                metadata={
                    "ip_address": ip_address,
                    "file_type": "avatar",
                    **(meta or {}),
                },
            )
        except Exception:
            pass

    try:
        user = await org_service.get_user(user_id)
        if user is None:
            await _audit(
                AuditAction.UPLOAD,
                status_val=AuditStatus.FAILED,
                error_msg="User not found",
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        is_admin = current_user["role"] in ["admin", "super_admin"]
        is_self = str(current_user["id"]) == str(user_id)

        if not is_self and not is_admin:
            await _audit(
                AuditAction.UPLOAD,
                status_val=AuditStatus.FAILED,
                error_msg="Not authorized",
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this user's avatar",
            )

        validate_image(file)

        processed_image = await process_avatar(file)

        workspace = get_workspace_path()
        org_avatar_dir = (
            workspace / "orgs" / str(user.organization_id) / "uploads" / "avatars"
        )
        org_avatar_dir.mkdir(parents=True, exist_ok=True)

        # SHA-256(user_id:org_id) → non-reversible, stable filename
        hash_input = f"{user_id}:{user.organization_id}"
        filename_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]
        filename = f"{filename_hash}.jpg"
        avatar_path = org_avatar_dir / filename

        with open(avatar_path, "wb") as f:
            f.write(processed_image)

        avatar_url = f"/uploads/orgs/{user.organization_id}/uploads/avatars/{filename}"

        update_command = UserUpdate(
            avatar_url=avatar_url,
        )
        await org_service.update_user(
            user_id=user_id,
            command=update_command,
            current_user_id=uuid.UUID(current_user["id"]),
        )

        await _audit(
            AuditAction.UPLOAD,
            meta={"filename": filename, "file_size": len(processed_image)},
        )

        return {"avatar_url": avatar_url}

    except EntityNotFoundError:
        await _audit(
            AuditAction.UPLOAD,
            status_val=AuditStatus.FAILED,
            error_msg="User not found",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        await _audit(
            AuditAction.UPLOAD, status_val=AuditStatus.FAILED, error_msg=str(e)
        )
        logger.exception("Failed to upload avatar")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar",
        )


@router.delete("/users/{user_id}/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_avatar(
    request: Request,
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    org_service: OrganizationServiceInterface = Depends(get_organization_service),
    audit_service: AuditService = Depends(get_audit_service),
) -> None:
    """Self-only unless admin. 403 otherwise."""
    ip_address = request.client.host if request.client else None
    actor_id = uuid.UUID(current_user["id"])
    org_id = uuid.UUID(current_user["org_id"]) if current_user.get("org_id") else None

    async def _audit(
        *, status_val: AuditStatus = AuditStatus.SUCCESS, error_msg=None, meta=None
    ):
        try:
            await audit_service.log_event(
                actor_id=actor_id,
                actor_type=AuditActorType(current_user.get("role", "user")),
                action=AuditAction.DELETE,
                resource_type=ResourceType.USER,
                resource_id=user_id,
                resource_name="avatar",
                organization_id=org_id,
                severity=(
                    AuditSeverity.WARNING
                    if status_val == AuditStatus.FAILED
                    else AuditSeverity.INFO
                ),
                category=AuditCategory.SECURITY,
                status=status_val,
                error_message=error_msg,
                metadata={
                    "ip_address": ip_address,
                    "file_type": "avatar",
                    **(meta or {}),
                },
            )
        except Exception:
            pass

    try:
        user = await org_service.get_user(user_id)
        if user is None:
            await _audit(status_val=AuditStatus.FAILED, error_msg="User not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        is_admin = current_user["role"] in ["admin", "super_admin"]
        is_self = str(current_user["id"]) == str(user_id)

        if not is_self and not is_admin:
            await _audit(status_val=AuditStatus.FAILED, error_msg="Not authorized")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this user's avatar",
            )

        if user.avatar_url:
            workspace = get_workspace_path()
            org_avatar_dir = (
                workspace / "orgs" / str(user.organization_id) / "uploads" / "avatars"
            )

            # Same hash as upload - locates the file deterministically
            hash_input = f"{user_id}:{user.organization_id}"
            filename_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]
            filename = f"{filename_hash}.jpg"
            avatar_path = org_avatar_dir / filename

            if avatar_path.exists():
                avatar_path.unlink()

        update_command = UserUpdate(
            avatar_url=None,
        )
        await org_service.update_user(
            user_id=user_id,
            command=update_command,
            current_user_id=uuid.UUID(current_user["id"]),
        )

        await _audit()

    except EntityNotFoundError:
        await _audit(status_val=AuditStatus.FAILED, error_msg="User not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        await _audit(status_val=AuditStatus.FAILED, error_msg=str(e))
        logger.exception("Failed to delete avatar")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete avatar",
        )
