# api/app/domain/common/exceptions.py

"""Domain exceptions: single source of truth for domain-layer errors."""

from typing import Any, Dict, Optional


class DomainException(Exception):
    """Base exception for all domain errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code
        self.context = context or {}
        super().__init__(self.message)

    @property
    def details(self) -> Dict[str, Any]:
        return self.context

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "code": self.code,
            "context": self.context,
        }


class BusinessRuleViolation(DomainException):
    """Raised when a domain-specific constraint is violated."""

    pass


class InvalidStateTransition(DomainException):
    """Raised when an entity lifecycle state machine rejects a transition."""

    pass


class InvariantViolation(DomainException):
    """Raised when an aggregate's internal consistency rule is violated."""

    pass


class EntityNotFoundError(DomainException):
    """Raised when a requested entity cannot be found by ID or unique key."""

    def __init__(self, entity_type: str, entity_id: Any, code: Optional[str] = None):
        self.entity_type = entity_type
        self.entity_id = entity_id

        message = f"{entity_type} with id '{entity_id}' not found"
        super().__init__(
            message=message,
            code=code or "ENTITY_NOT_FOUND",
            context={"entity_type": entity_type, "entity_id": str(entity_id)},
        )


class AggregateNotFoundError(EntityNotFoundError):
    """Specialized EntityNotFoundError for aggregate roots."""

    pass


class ValidationError(DomainException, ValueError):
    """Raised when domain validation fails. Inherits from ValueError so Pydantic field_validators catch it."""

    pass


class DuplicateEntityError(DomainException):
    """Raised when a unique constraint is violated.

    Two construction styles, auto-detected:
      - Domain: DuplicateEntityError(message, code, context)
      - Structured: DuplicateEntityError(entity_type, field, value) (positional or keyword)
    """

    entity_type: Optional[str]
    field: Optional[str]
    value: Any

    def __init__(
        self,
        message_or_entity_type: Optional[str] = None,
        code_or_field: Optional[str] = None,
        context_or_value: Any = None,
        *,
        entity_type: Optional[str] = None,
        field: Optional[str] = None,
        value: Any = None,
    ):
        if entity_type is not None:
            self.entity_type = entity_type
            self.field = field
            self.value = value
            generated_message = f"{entity_type} with {field}='{value}' already exists"
            context = {"entity_type": entity_type, "field": field, "value": value}
            super().__init__(
                message=message_or_entity_type or generated_message,
                code=code_or_field or "DUPLICATE_ENTITY",
                context=context,
            )
        elif (
            context_or_value is not None
            and not isinstance(context_or_value, dict)
            and code_or_field is not None
        ):
            self.entity_type = message_or_entity_type
            self.field = code_or_field
            self.value = context_or_value
            message = f"{message_or_entity_type} with {code_or_field}='{context_or_value}' already exists"
            context = {
                "entity_type": message_or_entity_type,
                "field": code_or_field,
                "value": context_or_value,
            }
            super().__init__(
                message=message,
                code="DUPLICATE_ENTITY",
                context=context,
            )
        else:
            self.entity_type = None
            self.field = None
            self.value = None
            super().__init__(
                message=message_or_entity_type or "Duplicate entity",
                code=code_or_field,
                context=(
                    context_or_value if isinstance(context_or_value, dict) else None
                ),
            )


class AuthorizationError(DomainException):
    """Domain-level authorization failures (role-based rules), not infra auth."""

    pass


class PermissionDeniedError(AuthorizationError):
    """Specific permission failure for role-based checks."""

    def __init__(self, message: str, code: str = "PERMISSION_DENIED"):
        super().__init__(
            message=message,
            code=code,
        )


class ConcurrencyError(DomainException):
    """Raised when concurrent modification is detected (e.g., optimistic-lock version mismatch)."""

    pass


class DomainServiceError(DomainException):
    """General failure in a domain service that doesn't fit other categories."""

    pass


class RepositoryError(DomainException):
    """Raised when a repository operation fails. Contract is domain-layer; implementation is infra."""

    pass


class ConfigurationError(DomainException):
    """Raised when domain configuration is invalid."""

    pass


__all__ = [
    "DomainException",
    "BusinessRuleViolation",
    "InvalidStateTransition",
    "InvariantViolation",
    "EntityNotFoundError",
    "AggregateNotFoundError",
    "ValidationError",
    "DuplicateEntityError",
    "AuthorizationError",
    "PermissionDeniedError",
    "ConcurrencyError",
    "DomainServiceError",
    "RepositoryError",
    "ConfigurationError",
]
