# api/app/presentation/api/error_handlers.py

"""Domain/application exceptions to standardized HTTP error responses."""

import logging
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import DBAPIError

from app.domain.common.exceptions import (
    AuthorizationError,
    BusinessRuleViolation,
    ConcurrencyError,
    ConfigurationError,
    DomainException,
    DuplicateEntityError,
    EntityNotFoundError,
    InvalidStateTransition,
    InvariantViolation,
    PermissionDeniedError,
    ValidationError,
)
from app.infrastructure.errors import safe_error_message

logger = logging.getLogger(__name__)


class ErrorResponse(BaseModel):

    error: str = Field(..., description="Error type or name")
    detail: str = Field(..., description="Detailed error message")
    timestamp: datetime = Field(..., description="Error timestamp")
    code: Optional[str] = Field(default=None, description="Optional error code")
    context: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional context"
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all domain/application exception handlers on the app."""

    # Pyright flags these handlers as unused because FastAPI invokes them via the
    # exception-handler decorator, not direct calls. Per-handler type:ignore is required.

    @app.exception_handler(EntityNotFoundError)
    async def _handle_entity_not_found(  # type: ignore[reportUnusedFunction]
        request: Request, exc: EntityNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                error="EntityNotFound",
                detail=safe_error_message(exc),
                timestamp=datetime.now(UTC),
                code=getattr(exc, "code", None),
                context=getattr(exc, "context", None),
            ).model_dump(mode="json", exclude_none=True),
        )

    @app.exception_handler(ValidationError)
    async def _handle_validation_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                error="ValidationError",
                detail=safe_error_message(exc),
                timestamp=datetime.now(UTC),
                code=getattr(exc, "code", None),
                context=getattr(exc, "context", None),
            ).model_dump(mode="json", exclude_none=True),
        )

    @app.exception_handler(DuplicateEntityError)
    async def _handle_duplicate_entity(  # type: ignore[reportUnusedFunction]
        request: Request, exc: DuplicateEntityError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(
                error="DuplicateEntity",
                detail=safe_error_message(exc),
                timestamp=datetime.now(UTC),
                code=getattr(exc, "code", None),
                context=getattr(exc, "context", None),
            ).model_dump(mode="json", exclude_none=True),
        )

    @app.exception_handler(PermissionDeniedError)
    async def _handle_permission_denied(  # type: ignore[reportUnusedFunction]
        request: Request, exc: PermissionDeniedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=ErrorResponse(
                error="PermissionDenied",
                detail=safe_error_message(exc),
                timestamp=datetime.now(UTC),
                code=getattr(exc, "code", None),
                context=getattr(exc, "context", None),
            ).model_dump(mode="json", exclude_none=True),
        )

    @app.exception_handler(AuthorizationError)
    async def _handle_authorization_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: AuthorizationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=ErrorResponse(
                error="Forbidden",
                detail=safe_error_message(exc),
                timestamp=datetime.now(UTC),
                code=getattr(exc, "code", None),
                context=getattr(exc, "context", None),
            ).model_dump(mode="json", exclude_none=True),
        )

    @app.exception_handler(BusinessRuleViolation)
    async def _handle_business_rule_violation(  # type: ignore[reportUnusedFunction]
        request: Request, exc: BusinessRuleViolation
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                error="BusinessRuleViolation",
                detail=safe_error_message(exc),
                timestamp=datetime.now(UTC),
                code=getattr(exc, "code", None),
                context=getattr(exc, "context", None),
            ).model_dump(mode="json", exclude_none=True),
        )

    @app.exception_handler(InvalidStateTransition)
    async def _handle_invalid_state_transition(  # type: ignore[reportUnusedFunction]
        request: Request, exc: InvalidStateTransition
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                error="InvalidStateTransition",
                detail=safe_error_message(exc),
                timestamp=datetime.now(UTC),
                code=getattr(exc, "code", None),
                context=getattr(exc, "context", None),
            ).model_dump(mode="json", exclude_none=True),
        )

    @app.exception_handler(InvariantViolation)
    async def _handle_invariant_violation(  # type: ignore[reportUnusedFunction]
        request: Request, exc: InvariantViolation
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                error="InvariantViolation",
                detail=safe_error_message(exc),
                timestamp=datetime.now(UTC),
                code=getattr(exc, "code", None),
                context=getattr(exc, "context", None),
            ).model_dump(mode="json", exclude_none=True),
        )

    @app.exception_handler(ConcurrencyError)
    async def _handle_concurrency_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: ConcurrencyError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(
                error="ConcurrencyError",
                detail=safe_error_message(exc),
                timestamp=datetime.now(UTC),
                code=getattr(exc, "code", None),
                context=getattr(exc, "context", None),
            ).model_dump(mode="json", exclude_none=True),
        )

    @app.exception_handler(ConfigurationError)
    async def _handle_configuration_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: ConfigurationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="ConfigurationError",
                detail=safe_error_message(exc),
                timestamp=datetime.now(UTC),
                code=getattr(exc, "code", None),
                context=getattr(exc, "context", None),
            ).model_dump(mode="json", exclude_none=True),
        )

    @app.exception_handler(DomainException)
    async def _handle_domain_exception(  # type: ignore[reportUnusedFunction]
        request: Request, exc: DomainException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                error="DomainError",
                detail=safe_error_message(exc),
                timestamp=datetime.now(UTC),
                code=getattr(exc, "code", None),
                context=getattr(exc, "context", None),
            ).model_dump(mode="json", exclude_none=True),
        )

    @app.exception_handler(DBAPIError)
    async def _handle_db_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: DBAPIError
    ) -> JSONResponse:
        # Full traceback (with SQL and bind params) goes to server logs only.
        # Response body is the classified, secret-free sentence.
        logger.exception("Unhandled database error reached HTTP boundary")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="DatabaseError",
                detail=safe_error_message(exc),
                timestamp=datetime.now(UTC),
                code="DATABASE_ERROR",
                context={
                    "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "exception_type": type(exc).__name__,
                },
            ).model_dump(mode="json", exclude_none=True),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_exception(  # type: ignore[reportUnusedFunction]
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception reached HTTP boundary")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="InternalServerError",
                detail="An unexpected error occurred",
                timestamp=datetime.now(UTC),
                code="UNKNOWN_500_ERROR",
                context={
                    "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "exception_type": type(exc).__name__,
                },
            ).model_dump(mode="json", exclude_none=True),
        )
