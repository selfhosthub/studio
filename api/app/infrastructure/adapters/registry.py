# api/app/infrastructure/adapters/registry.py

"""Registry that routes service execution requests to the right provider adapter."""

from typing import Any, Dict, Optional
from uuid import UUID
import logging

from app.application.interfaces.provider_adapter import IProviderAdapter
from app.domain.common.exceptions import ConfigurationError


logger = logging.getLogger(__name__)


class AdapterNotFoundError(ConfigurationError):
    pass


class ServiceNotSupportedError(ConfigurationError):
    pass


class AdapterRegistry:
    """Maps providers and services to adapter instances."""

    def __init__(self):
        self._adapters_by_name: Dict[str, IProviderAdapter] = {}
        self._adapters_by_id: Dict[UUID, IProviderAdapter] = {}
        self._adapters_by_service: Dict[str, IProviderAdapter] = {}

    def register_adapter(
        self,
        provider_name: str,
        adapter: IProviderAdapter,
        provider_id: Optional[UUID] = None,
    ) -> None:
        if provider_name in self._adapters_by_name:
            logger.warning(
                f"Adapter for '{provider_name}' already registered, overwriting"
            )

        if not adapter.provider_name:
            raise ValueError("Adapter must define provider_name property")

        if not adapter.supported_services:
            raise ValueError(
                "Adapter must define supported_services property (got empty list)"
            )

        self._adapters_by_name[provider_name] = adapter

        if provider_id:
            self._adapters_by_id[provider_id] = adapter

        for service_id in adapter.supported_services:
            if service_id in self._adapters_by_service:
                logger.warning(
                    f"Service '{service_id}' already registered to another adapter, "
                    f"overwriting with '{provider_name}' adapter"
                )
            self._adapters_by_service[service_id] = adapter

        logger.info(
            f"Registered adapter for '{provider_name}' "
            f"with {len(adapter.supported_services)} services: "
            f"{', '.join(adapter.supported_services)}"
        )

    def unregister_adapter(self, provider_name: str) -> None:
        if provider_name not in self._adapters_by_name:
            raise AdapterNotFoundError(
                f"No adapter registered for provider '{provider_name}'"
            )

        adapter = self._adapters_by_name[provider_name]

        del self._adapters_by_name[provider_name]

        provider_id = None
        for pid, adpt in self._adapters_by_id.items():
            if adpt is adapter:
                provider_id = pid
                break
        if provider_id:
            del self._adapters_by_id[provider_id]

        for service_id in adapter.supported_services:
            if (
                service_id in self._adapters_by_service
                and self._adapters_by_service[service_id] is adapter
            ):
                del self._adapters_by_service[service_id]

        logger.info(f"Unregistered adapter for '{provider_name}'")

    def get_adapter_by_name(self, provider_name: str) -> IProviderAdapter:
        if provider_name not in self._adapters_by_name:
            raise AdapterNotFoundError(
                f"No adapter registered for provider '{provider_name}'"
            )
        return self._adapters_by_name[provider_name]

    def get_adapter_by_id(self, provider_id: UUID) -> IProviderAdapter:
        if provider_id not in self._adapters_by_id:
            raise AdapterNotFoundError(
                f"No adapter registered for provider ID '{provider_id}'"
            )
        return self._adapters_by_id[provider_id]

    def get_adapter_for_service(self, service_id: str) -> IProviderAdapter:
        if service_id not in self._adapters_by_service:
            raise ServiceNotSupportedError(
                f"No adapter found for service '{service_id}'. "
                f"Available services: {', '.join(self._adapters_by_service.keys())}"
            )
        return self._adapters_by_service[service_id]

    def has_adapter_for_provider(self, provider_name: str) -> bool:
        return provider_name in self._adapters_by_name

    def has_adapter_for_service(self, service_id: str) -> bool:
        return service_id in self._adapters_by_service

    def list_registered_providers(self) -> list[str]:
        return list(self._adapters_by_name.keys())

    def list_supported_services(self) -> list[str]:
        return list(self._adapters_by_service.keys())

    def get_adapter_info(self) -> Dict[str, Dict[str, Any]]:
        info = {}
        for provider_name, adapter in self._adapters_by_name.items():
            info[provider_name] = {
                "provider_name": adapter.provider_name,
                "supported_services": adapter.supported_services,
                "service_count": len(adapter.supported_services),
            }
        return info

    def clear(self) -> None:
        self._adapters_by_name.clear()
        self._adapters_by_id.clear()
        self._adapters_by_service.clear()
        logger.info("Cleared all registered adapters")
