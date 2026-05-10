# api/app/application/interfaces/provider_adapter.py

"""Provider adapter interface for external service integration."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from uuid import UUID
from datetime import datetime, UTC


class ProviderExecutionResult:
    def __init__(
        self,
        success: bool,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        execution_time_ms: Optional[int] = None,
        provider_request_id: Optional[str] = None,
        warnings: Optional[list[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.data = data or {}
        self.error = error
        self.execution_time_ms = execution_time_ms
        self.provider_request_id = provider_request_id
        self.warnings = warnings or []
        self.metadata = metadata or {}
        self.executed_at = datetime.now(UTC)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "provider_request_id": self.provider_request_id,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "executed_at": self.executed_at.isoformat(),
        }


class CredentialValidationResult:
    def __init__(
        self,
        valid: bool,
        error: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        rate_limit_info: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.valid = valid
        self.error = error
        self.expires_at = expires_at
        self.rate_limit_info = rate_limit_info or {}
        self.metadata = metadata or {}
        self.validated_at = datetime.now(UTC)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "error": self.error,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "rate_limit_info": self.rate_limit_info,
            "metadata": self.metadata,
            "validated_at": self.validated_at.isoformat(),
        }


class HealthCheckResult:
    def __init__(
        self,
        healthy: bool,
        latency_ms: Optional[int] = None,
        error: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.healthy = healthy
        self.latency_ms = latency_ms
        self.error = error
        self.details = details or {}
        self.checked_at = datetime.now(UTC)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "healthy": self.healthy,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "details": self.details,
            "checked_at": self.checked_at.isoformat(),
        }


class IProviderAdapter(ABC):
    """Stateless, thread-safe adapter for one external provider. Credentials
    are passed per-call (not stored) to support multi-tenant isolation."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @property
    @abstractmethod
    def supported_services(self) -> list[str]:
        pass

    @abstractmethod
    async def execute_service(
        self,
        service_id: str,
        parameters: Dict[str, Any],
        credentials: Dict[str, Any],
        organization_id: UUID,
        timeout_seconds: Optional[int] = None,
        service_config: Optional[Dict[str, Any]] = None,
    ) -> ProviderExecutionResult:
        """Invoke an external provider API.

        Raises ValueError on unsupported service_id, TimeoutError on timeout.
        """
        pass

    @abstractmethod
    async def validate_credentials(
        self,
        credentials: Dict[str, Any],
    ) -> CredentialValidationResult:
        """Lightweight credential probe - must not perform actual work."""
        pass

    @abstractmethod
    async def health_check(self) -> HealthCheckResult:
        """Reachability probe. Must not require credentials when possible."""
        pass

    @abstractmethod
    def get_service_schema(self, service_id: str) -> Dict[str, Any]:
        """JSON Schema for service parameters. Raises ValueError if unsupported."""
        pass

    @abstractmethod
    def supports_service(self, service_id: str) -> bool:
        pass

    async def estimate_execution_time(
        self,
        service_id: str,
        parameters: Dict[str, Any],
    ) -> Optional[int]:
        """Optional. Seconds, or None if estimation is not supported."""
        return None

    async def get_rate_limit_info(
        self,
        credentials: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Optional. Rate limit status for the org's credentials, or None."""
        return None
