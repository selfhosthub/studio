# api/app/presentation/api/oauth_config.py

"""OAuth helpers that read config from provider DB records (config.oauth column)."""
import logging
import os
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status

from app.config.settings import settings
from app.domain.provider.repository import ProviderRepository

logger = logging.getLogger(__name__)


async def get_oauth_config_from_provider(
    provider_id: UUID,
    provider_repo: ProviderRepository,
) -> Dict[str, Any]:
    """OAuth config dict from provider.config.oauth. 404 if absent."""
    provider = await provider_repo.get_by_id(provider_id)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider {provider_id} not found",
        )

    oauth_config = provider.config.get("oauth")
    if not oauth_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{provider.name}' does not have OAuth configuration",
        )

    return oauth_config


async def get_all_oauth_configs(
    provider_repo: ProviderRepository,
) -> Dict[str, Dict[str, Any]]:
    """OAuth configs across providers, keyed by oauth_provider with scopes unioned.

    Multiple providers can share an oauth_provider (e.g. YouTube and Google both
    declare "google"); their scopes are merged so a single OAuth flow grants all
    required permissions.
    """
    providers = await provider_repo.find_active_providers(skip=0, limit=settings.DEFAULT_FETCH_LIMIT)

    configs: Dict[str, Dict[str, Any]] = {}
    for provider in providers:
        key = provider.config.get("oauth_provider")
        oauth = provider.config.get("oauth")
        if not key or not oauth:
            continue

        if key not in configs:
            configs[key] = dict(oauth)  # don't mutate provider config
        else:
            existing_scopes = set(configs[key].get("scopes", []))
            existing_scopes.update(oauth.get("scopes", []))
            configs[key]["scopes"] = sorted(existing_scopes)

    return configs


def get_platform_credentials(
    oauth_config: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str]]:
    """Platform-level (client_id, client_secret) from env vars named in oauth_config."""
    client_id = os.getenv(oauth_config.get("client_id_env", ""))
    client_secret = os.getenv(oauth_config.get("client_secret_env", ""))
    if client_id and client_secret:
        return client_id, client_secret
    return None, None
