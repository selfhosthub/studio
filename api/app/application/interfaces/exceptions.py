# api/app/application/interfaces/exceptions.py

"""Re-export of domain exceptions for application/presentation imports."""

from app.domain.common.exceptions import (
    AuthorizationError,
    BusinessRuleViolation,
    ConcurrencyError,
    DomainException,
    DuplicateEntityError,
    EntityNotFoundError,
    PermissionDeniedError,
    RepositoryError,
    ValidationError,
)

__all__ = [
    "AuthorizationError",
    "BusinessRuleViolation",
    "ConcurrencyError",
    "DomainException",
    "DuplicateEntityError",
    "EntityNotFoundError",
    "PermissionDeniedError",
    "RepositoryError",
    "ValidationError",
]
