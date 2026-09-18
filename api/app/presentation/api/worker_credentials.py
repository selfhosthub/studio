# api/app/presentation/api/worker_credentials.py

"""Internal endpoints for workers to fetch provider credentials and upload files."""
import logging
import mimetypes
from datetime import datetime, timedelta, UTC
from io import BytesIO
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx

from app.domain.provider.credential_validity import serve_stored_token
from app.domain.provider.models import CredentialType, ProviderCredential
from app.domain.provider.repository import (
    ProviderCredentialRepository,
    ProviderRepository,
    ProviderServiceRepository,
)
from app.domain.queue.models import QueuedJob
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.persistence.database import get_db_session_service
from app.infrastructure.repositories.step_execution_repository import SQLAlchemyStepExecutionRepository
from app.application.services.audit_service import AuditService
from app.presentation.api.uploads import spooled_upload
from app.presentation.api.dependencies import (
    get_audit_service,
    get_org_file_service_bypass,
    get_provider_credential_repository_bypass,
    get_provider_repository_bypass,
    get_provider_service_repository,
)
from app.presentation.api.worker_auth import (
    WorkerIdentity,
    require_worker,
    require_worker_job,
    resolve_worker_job,
)
from app.application.services.org_file import (
    OrgFileService,
)
from app.application.interfaces import EntityNotFoundError
from app.presentation.api.oauth_config import (
    get_oauth_config_from_provider,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Worker Credentials"])


class TokenResponse(BaseModel):
    """Access token for a provider."""

    access_token: str
    token_type: str
    expires_in: Optional[int] = None  # seconds until expiry


class CredentialResponse(BaseModel):
    """Full credential payload for non-OAuth types."""

    credential_type: str
    credentials: Dict[str, Any]


async def refresh_oauth_token(
    credential: Any,
    provider_repo: ProviderRepository,
    credential_repo: ProviderCredentialRepository,
) -> str:
    if serve_stored_token(credential):
        return credential.credentials.get("access_token")

    refresh_token = credential.credentials.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No refresh token available. Re-authorize the application.",
        )

    oauth_config = await get_oauth_config_from_provider(
        credential.provider_slug, provider_repo
    )

    # client creds come from the credential's DB row
    client_id = credential.credentials.get("client_id")
    client_secret = credential.credentials.get("client_secret")

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth not configured. No client credentials available.",
        )

    client_id_param = oauth_config.get("client_id_param", "client_id")
    token_request_data = {
        client_id_param: client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    try:
        async with httpx.AsyncClient() as client:
            headers = {"Accept": "application/json"}
            response = await client.post(
                oauth_config["token_url"],
                data=token_request_data,
                headers=headers,
            )

            if response.status_code != 200:
                logger.error(
                    f"Token refresh failed: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Token refresh failed. Re-authorize may be required.",
                )

            tokens = response.json()
    except httpx.RequestError as e:
        logger.error(f"Token refresh network error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to connect to OAuth provider",
        )

    expires_at = None
    if "expires_in" in tokens:
        expires_at = datetime.now(UTC) + timedelta(seconds=tokens["expires_in"])

    # client_id/client_secret are guaranteed present (validated above).
    credential.credentials = {
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token", refresh_token),
        "token_type": tokens.get("token_type", "Bearer"),
        "scope": tokens.get("scope", credential.credentials.get("scope")),
    }
    credential.expires_at = expires_at
    credential.updated_at = datetime.now(UTC)

    await credential_repo.update(credential)

    logger.info(f"Refreshed OAuth token for credential {credential.id}")

    return tokens.get("access_token")


async def _deny(
    audit: AuditService,
    *,
    status_code: int,
    detail: str,
    reason: str,
    worker_id: UUID,
    credential_id: str,
    job_id: Any = None,
    organization_id: Optional[UUID] = None,
) -> HTTPException:
    """Log and audit a refused credential request, and return the error to raise."""
    logger.warning(
        "Credential request denied: reason=%s worker=%s job=%s credential=%s",
        reason,
        str(worker_id)[:8],
        str(job_id)[:8] if job_id else None,
        str(credential_id)[:8],
    )
    await audit.log_worker_credential_denied(
        worker_id=worker_id,
        credential_id=credential_id,
        reason=reason,
        organization_id=organization_id,
        job_id=str(job_id) if job_id else None,
    )
    return HTTPException(status_code=status_code, detail=detail)


async def _authorize_credential_for_job(
    credential_id: str,
    worker_uuid: UUID,
    job: QueuedJob,
    credential_repo: ProviderCredentialRepository,
    provider_service_repo: ProviderServiceRepository,
    provider_repo: ProviderRepository,
    audit: AuditService,
) -> ProviderCredential:
    """Enforce that the worker's claimed job is entitled to this credential.

    Layered defense beyond JWT + registration. All checks fail-closed: a job
    that does not declare the exact credential, provider, and a service that
    belongs to that provider cannot retrieve a token.
    """
    input_data = job.input_data or {}

    # 1. Fail-closed credential binding. The worker only calls this endpoint
    #    when it needs a credential, so a job with no declared credential_id
    #    (or a mismatched one) has no business fetching a token.
    job_credential_id = input_data.get("credential_id")
    if not job_credential_id or str(job_credential_id) != credential_id:
        raise await _deny(
            audit,
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Credential does not belong to this worker's active job",
            reason="credential_id_mismatch",
            worker_id=worker_uuid,
            job_id=job.id,
            credential_id=credential_id,
            organization_id=job.organization_id,
        )

    credential = await credential_repo.get_by_id(UUID(credential_id))
    if not credential:
        raise await _deny(
            audit,
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
            reason="credential_not_found",
            worker_id=worker_uuid,
            job_id=job.id,
            credential_id=credential_id,
            organization_id=job.organization_id,
        )

    if not credential.is_active:
        raise await _deny(
            audit,
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credential is inactive",
            reason="credential_inactive",
            worker_id=worker_uuid,
            job_id=job.id,
            credential_id=credential_id,
            organization_id=job.organization_id,
        )

    # 2. Org isolation: the credential must belong to the job's organization.
    if credential.organization_id != job.organization_id:
        raise await _deny(
            audit,
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Credential does not belong to this worker's active job",
            reason="org_mismatch",
            worker_id=worker_uuid,
            job_id=job.id,
            credential_id=credential_id,
            organization_id=job.organization_id,
        )

    # 3. Credential <-> provider binding: the job must target the provider that
    #    owns this credential. Compared by slug, since the job carries whichever
    #    version row was current when it was enqueued.
    job_provider_id = input_data.get("provider_id")
    job_provider = None
    if job_provider_id:
        try:
            job_provider = await provider_repo.get_by_id(UUID(str(job_provider_id)))
        except ValueError:
            job_provider = None
    if not job_provider or job_provider.slug != credential.provider_slug:
        raise await _deny(
            audit,
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Credential does not belong to this worker's active job",
            reason="provider_mismatch",
            worker_id=worker_uuid,
            job_id=job.id,
            credential_id=credential_id,
            organization_id=job.organization_id,
        )

    # 4. Service <-> provider binding: the job's service_id must resolve to an
    #    active ProviderService owned by the credential's provider.
    job_service_id = input_data.get("service_id")
    if not job_service_id:
        raise await _deny(
            audit,
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Credential does not belong to this worker's active job",
            reason="service_id_missing",
            worker_id=worker_uuid,
            job_id=job.id,
            credential_id=credential_id,
            organization_id=job.organization_id,
        )

    service = await provider_service_repo.get_by_service_id(
        str(job_service_id), skip=0, limit=1
    )
    service_provider = (
        await provider_repo.get_by_id(service.provider_id) if service else None
    )
    if (
        not service
        or not service.is_active
        or not service_provider
        or service_provider.slug != credential.provider_slug
    ):
        raise await _deny(
            audit,
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Credential does not belong to this worker's active job",
            reason="service_provider_mismatch",
            worker_id=worker_uuid,
            job_id=job.id,
            credential_id=credential_id,
            organization_id=job.organization_id,
        )

    return credential


async def _worker_credential(
    credential_id: str,
    job_id: Optional[str],
    worker: WorkerIdentity,
    session: AsyncSession,
    credential_repo: ProviderCredentialRepository,
    provider_service_repo: ProviderServiceRepository,
    provider_repo: ProviderRepository,
    audit: AuditService,
) -> ProviderCredential:
    """The only route to a decrypted credential for a worker: its running job must name it."""
    job = await resolve_worker_job(worker.worker_id, job_id, session)
    if not job:
        raise await _deny(
            audit,
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active job found for this worker",
            reason="no_active_job",
            worker_id=worker.worker_id,
            job_id=job_id,
            credential_id=credential_id,
        )
    return await _authorize_credential_for_job(
        credential_id,
        worker.worker_id,
        job,
        credential_repo,
        provider_service_repo,
        provider_repo,
        audit,
    )


@router.get("/credentials/{credential_id}/token", response_model=TokenResponse)
async def get_credential_token(
    credential_id: str,
    job_id: Optional[str] = Query(None),
    worker: WorkerIdentity = Depends(require_worker),
    provider_repo: ProviderRepository = Depends(
        get_provider_repository_bypass
    ),
    credential_repo: ProviderCredentialRepository = Depends(
        get_provider_credential_repository_bypass
    ),
    provider_service_repo: ProviderServiceRepository = Depends(
        get_provider_service_repository
    ),
    session: AsyncSession = Depends(get_db_session_service),
    audit: AuditService = Depends(get_audit_service),
) -> TokenResponse:
    """Fresh access token. OAuth tokens are auto-refreshed when expired."""
    credential = await _worker_credential(
        credential_id,
        job_id,
        worker,
        session,
        credential_repo,
        provider_service_repo,
        provider_repo,
        audit,
    )

    if credential.credential_type == CredentialType.OAUTH2:
        access_token = await refresh_oauth_token(
            credential, provider_repo, credential_repo
        )

        expires_in = None
        if credential.expires_at:
            delta = credential.expires_at - datetime.now(UTC)
            expires_in = max(0, int(delta.total_seconds()))

        return TokenResponse(
            access_token=access_token,
            token_type=credential.credentials.get("token_type", "Bearer"),
            expires_in=expires_in,
        )

    access_token = (
        credential.credentials.get("access_token")
        or credential.credentials.get("api_key")
        or credential.credentials.get("token")
    )

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credential does not contain an access token",
        )

    return TokenResponse(
        access_token=access_token,
        token_type=credential.credentials.get("token_type", "Bearer"),
        expires_in=None,
    )


@router.get("/credentials/{credential_id}", response_model=CredentialResponse)
async def get_credential(
    credential_id: str,
    job_id: Optional[str] = Query(None),
    worker: WorkerIdentity = Depends(require_worker),
    provider_repo: ProviderRepository = Depends(
        get_provider_repository_bypass
    ),
    credential_repo: ProviderCredentialRepository = Depends(
        get_provider_credential_repository_bypass
    ),
    provider_service_repo: ProviderServiceRepository = Depends(
        get_provider_service_repository
    ),
    session: AsyncSession = Depends(get_db_session_service),
    audit: AuditService = Depends(get_audit_service),
) -> CredentialResponse:
    """Full credential payload (use for basic auth where username/password is required)."""
    credential = await _worker_credential(
        credential_id,
        job_id,
        worker,
        session,
        credential_repo,
        provider_service_repo,
        provider_repo,
        audit,
    )
    return CredentialResponse(
        credential_type=credential.credential_type.value,
        credentials=credential.credentials,
    )


class FileUploadResponse(BaseModel):
    resource_id: str
    virtual_path: str


class FileRegisterRequest(BaseModel):
    """Metadata-only file registration for `storage_mode=local` workers.

    The worker has already atomically written the bytes at the canonical
    path; the API stats the file, verifies size+checksum, and creates
    the OrgFile row without ever touching the wire payload."""

    filename: str  # display_name (pre-sanitization), used by the UI
    file_extension: str  # leading dot included, e.g. ".mp4"
    mime_type: str
    size: int
    checksum: str  # sha256 hex digest the worker computed pre-write
    has_thumbnail: bool = False  # worker also wrote `{base}-thumbnail.jpg`
    job_id: Optional[str] = None


async def _worker_job(
    worker: WorkerIdentity,
    job_id: Optional[str],
    session: AsyncSession,
) -> QueuedJob:
    """The job a worker may write to, which must carry an instance."""
    job = await require_worker_job(worker.worker_id, job_id, session)
    if not job.instance_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job has no associated instance",
        )
    return job


@router.post(
    "/files/register",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_worker_local_file(
    request: FileRegisterRequest,
    worker: WorkerIdentity = Depends(require_worker),
    service: OrgFileService = Depends(get_org_file_service_bypass),
    session: AsyncSession = Depends(get_db_session_service),
) -> FileUploadResponse:
    """Register a worker-written file at the canonical path.

    Companion to `/files/upload` for `storage_mode=local` workers. The
    worker has already written the bytes to
    `/workspace/orgs/{org_id}/instances/{instance_id}/{sanitized_filename}`;
    we stat that file, recompute the checksum, and create the OrgFile
    row. The worker never controls the path - the API derives it from
    the JWT-bound job, so a hostile or buggy `filename` value cannot
    escape the instance directory.

    404: file absent at the derived path → worker should retry via the
    multipart `/files/upload` endpoint as fallback.
    422: size or checksum mismatch → bytes on disk are not what the
    worker claims; worker may retry.
    """
    job = await _worker_job(worker, request.job_id, session)
    # _worker_job rejects jobs without an instance_id (400), so it is
    # non-None here; assert it so the type narrows for the calls below.
    assert job.instance_id is not None

    step_key = job.input_data.get("step_id") if job.input_data else None
    if not step_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job payload missing step_id",
        )

    step_repo = SQLAlchemyStepExecutionRepository(session)
    step_execution = await step_repo.get_by_instance_and_key(job.instance_id, step_key)
    job_execution_id = step_execution.id if step_execution else None

    try:
        resource = await service.register_step_file_in_place(
            instance_id=job.instance_id,
            step_key=step_key,
            organization_id=job.organization_id,
            expected_size=request.size,
            expected_checksum=request.checksum,
            mime_type=request.mime_type,
            file_extension=request.file_extension,
            display_name=request.filename,
            job_execution_id=job_execution_id,
            has_caller_thumbnail=request.has_thumbnail,
        )
    except FileNotFoundError as e:
        logger.warning(f"Worker register-in-place miss: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Worker-declared file not present at expected path",
        )
    except ValueError as e:
        logger.warning(f"Worker register-in-place integrity failure: {e}")
        raise HTTPException(
            status_code=422,
            detail="File integrity check failed (size or checksum mismatch)",
        )
    except Exception as exc:
        logger.error(f"Worker file register failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File register failed",
        )

    logger.info(
        f"File registered in place: step={step_key} "
        f"job={str(job.id)[:8]} size={request.size} "
        f"resource={str(resource.id)[:8]}"
    )

    return FileUploadResponse(
        resource_id=str(resource.id), virtual_path=resource.virtual_path
    )


@router.post("/files/upload", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file_for_worker(
    file: UploadFile = File(...),
    thumbnail: Optional[UploadFile] = File(None),
    filename: Optional[str] = Form(None),
    job_id: Optional[str] = Form(None),
    worker: WorkerIdentity = Depends(require_worker),
    service: OrgFileService = Depends(get_org_file_service_bypass),
    session: AsyncSession = Depends(get_db_session_service),
) -> FileUploadResponse:
    """Store a worker-uploaded file as an OrgFile."""
    job = await _worker_job(worker, job_id, session)
    assert job.instance_id is not None

    step_key = job.input_data.get("step_id") if job.input_data else None
    if not step_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job payload missing step_id",
        )

    step_repo = SQLAlchemyStepExecutionRepository(session)
    step_execution = await step_repo.get_by_instance_and_key(job.instance_id, step_key)

    job_execution_id = step_execution.id if step_execution else None
    instance_step_id = None

    display_name = filename or file.filename or "worker_output"

    file_extension = ""
    ext_index = display_name.rfind(".")
    if ext_index != -1:
        file_extension = display_name[ext_index:]

    raw_content_type = file.content_type
    mime_type: str
    if not raw_content_type or raw_content_type == "application/octet-stream":
        guessed, _encoding = mimetypes.guess_type(display_name)
        mime_type = guessed or "application/octet-stream"
    else:
        mime_type = str(raw_content_type)

    file_stream, file_size = spooled_upload(file)

    thumbnail_io = None
    if thumbnail is not None:
        thumbnail_io = BytesIO(await thumbnail.read())

    try:
        resource = await service.upload_file_to_step(
            instance_id=job.instance_id,
            step_key=step_key,
            organization_id=job.organization_id,
            file_content=file_stream,
            file_size=file_size,
            mime_type=mime_type,
            file_extension=file_extension,
            display_name=display_name,
            job_execution_id=job_execution_id,
            instance_step_id=instance_step_id,
            caller_thumbnail_content=thumbnail_io,
        )
    except Exception as exc:
        logger.error(f"Worker file upload failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File upload failed",
        )

    virtual_path = (
        f"/orgs/{job.organization_id}/instances/{job.instance_id}/{display_name}"
    )

    logger.info(f"File uploaded: step={step_key} job={str(job.id)[:8]} size={file_size} resource={str(resource.id)[:8]}")

    return FileUploadResponse(resource_id=str(resource.id), virtual_path=virtual_path)


@router.get("/files/{file_id}/download")
async def download_file_for_worker(
    file_id: str,
    job_id: Optional[str] = Query(None),
    worker: WorkerIdentity = Depends(require_worker),
    service: OrgFileService = Depends(get_org_file_service_bypass),
    session: AsyncSession = Depends(get_db_session_service),
):
    """Serve a file from the organization of the worker's running job."""
    job = await resolve_worker_job(worker.worker_id, job_id, session)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active job found for this worker",
        )
    try:
        file_path, mime_type = await service.get_resource_file_path(
            UUID(file_id), organization_id=job.organization_id
        )

        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found on disk",
            )

        return FileResponse(
            path=str(file_path),
            media_type=mime_type,
            filename=file_path.name,
        )
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file ID format",
        )
