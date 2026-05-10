# api/app/infrastructure/adapters/provider_loader.py

"""Loads provider configurations from the DB and registers their adapters."""

import logging
from typing import Any, Dict, Optional, Union
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.provider.models import Provider
from app.infrastructure.persistence.models import ProviderModel, ProviderServiceModel
from app.infrastructure.adapters.generic_http_adapter import GenericHTTPAdapter
from app.infrastructure.adapters.webhook_adapter import WebhookAdapter
from app.infrastructure.adapters.registry import AdapterRegistry
from app.application.interfaces.provider_adapter import IProviderAdapter

logger = logging.getLogger(__name__)


def build_adapter_provider_config(
    provider: Union[ProviderModel, Provider],
) -> Dict[str, Any]:
    """Shape a provider record into the dict shape adapters expect."""
    config = provider.config or {}
    adapter_config = config.get("adapter_config", {})
    return {
        "id": str(provider.id),
        "name": provider.name,
        "description": provider.description,
        "base_url": provider.endpoint_url,
        "adapter_type": config.get("adapter_type", "generic_http"),
        "adapter_config": {
            **adapter_config,
            # auth lives at top level of adapter-config.json; fall back to the
            # nested form for historical configs.
            "auth": config.get("auth", adapter_config.get("auth", {})),
        },
        "validation_config": config.get("validation_config", {}),
        "health_check_endpoint": config.get("health_check_endpoint", "/"),
        "webhook_config": config.get("webhook_config", {}),
    }


class ProviderLoader:
    """Loads active providers from DB and registers adapters in the registry."""

    def __init__(self, registry: AdapterRegistry):
        self.registry = registry

    async def load_provider(
        self, session: AsyncSession, provider_name: str
    ) -> Optional[IProviderAdapter]:
        result = await session.execute(
            select(ProviderModel).where(
                ProviderModel.name == provider_name, ProviderModel.status == "ACTIVE"
            )
        )
        provider_model = result.scalar_one_or_none()

        if not provider_model:
            logger.warning(f"Provider '{provider_name}' not found in database")
            return None

        provider_config = build_adapter_provider_config(provider_model)

        services = await self.get_provider_services(session, provider_model.id)
        service_ids = [service["service_id"] for service in services]

        adapter_type = provider_config["adapter_type"]

        if adapter_type == "generic_http":
            adapter = GenericHTTPAdapter(
                provider_config, supported_services=service_ids
            )
            logger.info(
                f"Created GenericHTTPAdapter for provider '{provider_name}' with {len(service_ids)} services"
            )
        else:
            logger.error(f"Unsupported adapter type: {adapter_type}")
            return None

        self.registry.register_adapter(
            provider_name=provider_name, adapter=adapter, provider_id=provider_model.id
        )

        logger.info(
            f"Registered adapter for provider '{provider_name}' (ID: {provider_model.id})"
        )

        return adapter

    async def load_all_providers(self, session: AsyncSession) -> int:
        """Load all active providers; returns count loaded."""
        result = await session.execute(
            select(ProviderModel).where(ProviderModel.status == "ACTIVE")
        )
        providers = result.scalars().all()

        loaded_count = 0

        for provider_model in providers:
            try:
                provider_config = build_adapter_provider_config(provider_model)

                services = await self.get_provider_services(session, provider_model.id)
                service_ids = [service["service_id"] for service in services]

                is_internal = provider_model.config.get("internal", False)
                if is_internal:
                    logger.info(
                        f"Skipping adapter creation for internal provider '{provider_model.name}' "
                        f"(no external endpoint required)"
                    )
                    continue

                adapter_type = provider_config["adapter_type"]
                if adapter_type == "generic_http":
                    if not provider_config.get("base_url"):
                        # Queue-based providers run without an HTTP adapter.
                        logger.debug(
                            f"No HTTP adapter for '{provider_model.name}': "
                            f"generic_http requires base_url (queue-based providers skip this)"
                        )
                        continue
                    adapter = GenericHTTPAdapter(
                        provider_config, supported_services=service_ids
                    )
                else:
                    logger.warning(
                        f"Skipping provider '{provider_model.name}': "
                        f"unsupported adapter type '{adapter_type}'"
                    )
                    continue

                self.registry.register_adapter(
                    provider_name=provider_model.name,
                    adapter=adapter,
                    provider_id=provider_model.id,
                )

                loaded_count += 1
                logger.info(f"Loaded provider: {provider_model.name}")

            except Exception as e:
                logger.error(
                    f"Failed to load provider '{provider_model.name}': {e}",
                )

        logger.info(f"Loaded {loaded_count} providers from database")
        return loaded_count

    async def get_provider_services(
        self, session: AsyncSession, provider_id: UUID
    ) -> list[Dict[str, Any]]:
        result = await session.execute(
            select(ProviderServiceModel).where(
                ProviderServiceModel.provider_id == provider_id,
                ProviderServiceModel.is_active == True,
            )
        )
        services = result.scalars().all()

        return [
            {
                "id": str(service.id),
                "service_id": service.service_id,
                "display_name": service.display_name,
                "description": service.description,
                "service_type": service.service_type.value,
                "parameter_schema": service.parameter_schema,
                "result_schema": service.result_schema,
                "example_parameters": service.example_parameters,
            }
            for service in services
        ]


async def register_single_provider(
    session: AsyncSession, registry: AdapterRegistry, provider_id: UUID
) -> bool:
    """Register one provider after package install - no API restart required."""
    from app.infrastructure.persistence.models import (
        ProviderModel,
        ProviderServiceModel,
    )

    result = await session.execute(
        select(ProviderModel).where(
            ProviderModel.id == provider_id, ProviderModel.status == "ACTIVE"
        )
    )
    provider_model = result.scalar_one_or_none()

    if not provider_model:
        logger.debug(
            f"Provider {provider_id} not found or not active (may be config-only)"
        )
        return False

    try:
        provider_config = build_adapter_provider_config(provider_model)

        services_result = await session.execute(
            select(ProviderServiceModel).where(
                ProviderServiceModel.provider_id == provider_id,
                ProviderServiceModel.is_active == True,
            )
        )
        services = services_result.scalars().all()
        service_ids = [service.service_id for service in services]

        is_internal = provider_model.config.get("internal", False)
        if is_internal:
            logger.info(
                f"Skipping adapter creation for internal provider '{provider_model.name}' "
                f"(no external endpoint required)"
            )
            return False

        adapter_type = provider_config["adapter_type"]
        if adapter_type == "generic_http":
            if not provider_config.get("base_url"):
                # Queue-based providers run without an HTTP adapter.
                logger.debug(
                    f"No HTTP adapter for '{provider_model.name}': "
                    f"generic_http requires base_url (queue-based providers skip this)"
                )
                return False
            adapter = GenericHTTPAdapter(
                provider_config, supported_services=service_ids
            )
        else:
            logger.warning(
                f"Skipping provider '{provider_model.name}': "
                f"unsupported adapter type '{adapter_type}'"
            )
            return False

        registry.register_adapter(
            provider_name=provider_model.name,
            adapter=adapter,
            provider_id=provider_model.id,
        )

        logger.info(
            f"Registered adapter for provider '{provider_model.name}' (ID: {provider_model.id})"
        )
        return True

    except Exception as e:
        logger.error(
            f"Failed to register adapter for provider {provider_id}: {e}",
        )
        return False


async def initialize_providers(session: AsyncSession, registry: AdapterRegistry) -> int:
    """Register the built-in webhook adapter and load DB providers at startup."""
    builtin_count = 0

    webhook_adapter = WebhookAdapter()
    registry.register_adapter(
        provider_name="webhook",
        adapter=webhook_adapter,
    )
    builtin_count += 1
    logger.info("Registered built-in WebhookAdapter for webhook step types")

    loader = ProviderLoader(registry)
    count = await loader.load_all_providers(session)

    total_count = count + builtin_count
    logger.info(
        f"Provider initialization complete: {total_count} providers loaded ({count} from database, {builtin_count} built-in)"
    )
    return total_count
