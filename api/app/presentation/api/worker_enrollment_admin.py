# api/app/presentation/api/worker_enrollment_admin.py

"""Super-admin management of worker join tokens and enrollment credentials."""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.config.queues import allowed_queues
from app.infrastructure.security.worker_enrollment_store import (
    create_join_token,
    decide_enrollment_request,
    list_enrollment_requests,
    list_enrollments,
    list_join_tokens,
    revoke_enrollment,
)
from app.presentation.api.dependencies import (
    CurrentUser,
    get_current_user,
    require_super_admin,
)
from app.presentation.api.models.worker import (
    EnrollmentRequestApproveRequest,
    EnrollmentRequestResponse,
    JoinTokenCreateRequest,
    JoinTokenCreateResponse,
    JoinTokenResponse,
    WorkerEnrollmentResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/workers/join-tokens",
    response_model=JoinTokenCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mint a worker join token",
    description="""
    Mint a single-use, expiring token a worker exchanges for its own credential.
    Super-admin only.

    The token is returned once and never again: only its hash is stored.
    """,
)
async def mint_join_token(
    request: JoinTokenCreateRequest,
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
) -> JoinTokenCreateResponse:
    """400 if a named queue is outside the operator's allowed set."""
    allowed = allowed_queues()
    refused = [q for q in request.queues if q not in allowed]
    if refused:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Queue(s) not in the allowed set: {', '.join(sorted(refused))}. "
            "The operator can widen it via SHS_ALLOWED_QUEUES.",
        )

    created = await create_join_token(
        label=request.label,
        queues=request.queues,
        ttl_seconds=request.ttl_seconds,
        created_by=UUID(user["id"]),
    )
    logger.info(
        f"Join token minted: {request.label} "
        f"(id={created['id']}, queues={sorted(request.queues)})"
    )
    return JoinTokenCreateResponse(**created)


@router.get(
    "/workers/join-tokens",
    response_model=List[JoinTokenResponse],
    summary="List worker join tokens",
    description="Outstanding and spent join tokens. Super-admin only.",
)
async def get_join_tokens(
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
) -> List[JoinTokenResponse]:
    return [JoinTokenResponse(**row) for row in await list_join_tokens()]


@router.get(
    "/workers/enrollments",
    response_model=List[WorkerEnrollmentResponse],
    summary="List worker enrollments",
    description="Every worker credential, live and revoked. Super-admin only.",
)
async def get_enrollments(
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
) -> List[WorkerEnrollmentResponse]:
    return [WorkerEnrollmentResponse(**row) for row in await list_enrollments()]


@router.delete(
    "/workers/enrollments/{enrollment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a worker enrollment",
    description="""
    Revoke one worker's credential. Every worker registered with it is
    deregistered at once, so its JWT stops working, and it cannot register
    again. Super-admin only.
    """,
)
async def revoke(
    enrollment_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
) -> None:
    """404 if the enrollment does not exist or was already revoked."""
    if not await revoke_enrollment(enrollment_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found or already revoked.",
        )
    logger.info(f"Worker enrollment revoked: {enrollment_id}")


@router.get(
    "/workers/enrollment-requests",
    response_model=List[EnrollmentRequestResponse],
    summary="List worker enrollment requests",
    description="Shared-secret workers from outside the deployment, pending first. Super-admin only.",
)
async def get_enrollment_requests(
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
) -> List[EnrollmentRequestResponse]:
    return [EnrollmentRequestResponse(**row) for row in await list_enrollment_requests()]


@router.post(
    "/workers/enrollment-requests/{request_id}/approve",
    response_model=EnrollmentRequestResponse,
    summary="Approve a worker enrollment request",
    description="""
    Grant a pending worker its own credential, scoped to the given queues or to
    the queues it asked for. The worker collects the credential on its next
    poll. Super-admin only.
    """,
)
async def approve_enrollment_request(
    request_id: UUID,
    request: Optional[EnrollmentRequestApproveRequest] = None,
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
) -> EnrollmentRequestResponse:
    """400 if a granted queue is outside the operator's allowed set; 404 if the request is not pending."""
    queues = request.queues if request else None
    if queues is not None:
        allowed = allowed_queues()
        refused = [q for q in queues if q not in allowed]
        if refused:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Queue(s) not in the allowed set: {', '.join(sorted(refused))}. "
                "The operator can widen it via SHS_ALLOWED_QUEUES.",
            )
    decided = await decide_enrollment_request(
        request_id, approve=True, queues=queues, decided_by=UUID(user["id"])
    )
    if decided is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment request not found or already decided.",
        )
    logger.info(
        f"Worker enrollment request approved: {request_id} (queues={sorted(decided['queues'])})"
    )
    return EnrollmentRequestResponse(**decided)


@router.post(
    "/workers/enrollment-requests/{request_id}/reject",
    response_model=EnrollmentRequestResponse,
    summary="Reject a worker enrollment request",
    description="Refuse a pending worker. Super-admin only.",
)
async def reject_enrollment_request(
    request_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
) -> EnrollmentRequestResponse:
    """404 if the request is not pending."""
    decided = await decide_enrollment_request(
        request_id, approve=False, queues=None, decided_by=UUID(user["id"])
    )
    if decided is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment request not found or already decided.",
        )
    logger.info(f"Worker enrollment request rejected: {request_id}")
    return EnrollmentRequestResponse(**decided)
