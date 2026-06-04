# workers/shared/utils/credential_client.py

"""
HTTP client for workers to fetch fresh credential tokens from API.

Workers call /api/v1/internal/credentials/{id}/token to get fresh tokens
immediately before making authenticated API calls. This ensures OAuth tokens
are always fresh (auto-refreshed by API if expired).

Security: Uses WORKER_SHARED_SECRET header for authentication.
"""
import logging
import time
from typing import Dict, Optional, Tuple
import httpx

from shared.settings import settings

logger = logging.getLogger(__name__)

# Cached tokens are valid for this many seconds before re-fetching.
# OAuth tokens from the API are typically valid for 60min; 5min cache
# reduces API calls while keeping the staleness window small.
_TOKEN_CACHE_TTL_S = settings.TOKEN_CACHE_TTL

# Maximum number of cached credential tokens before evicting oldest entries.
_TOKEN_CACHE_MAX_SIZE = settings.TOKEN_CACHE_MAX_SIZE


class CredentialClient:
    """Fetches fresh credential tokens from API for worker use."""

    def __init__(self):
        self.api_base_url = settings.API_BASE_URL
        self.worker_secret = settings.WORKER_SHARED_SECRET
        # Token cache: credential_id -> (token, expiry_timestamp)
        self._token_cache: Dict[str, Tuple[str, float]] = {}
        # Reusable async client for connection pooling
        self._async_client: Optional[httpx.AsyncClient] = None

        if not self.worker_secret:
            logger.warning(
                "WORKER_SHARED_SECRET not set - credential fetching disabled"
            )

    async def get_token(
        self, credential_id: str, oauth_provider: Optional[str] = None
    ) -> Optional[str]:
        """Fetch fresh access token, using cache when valid."""
        if not self.worker_secret:
            logger.error("Cannot fetch token: WORKER_SHARED_SECRET not configured")
            return None

        # Check cache first
        cached = self._token_cache.get(credential_id)
        if cached:
            token, expiry = cached
            if time.monotonic() < expiry:
                logger.debug(
                    f"Using cached token for credential {credential_id[:8]}..."
                )
                return token
            else:
                # Evict expired entry
                del self._token_cache[credential_id]

        url = f"{self.api_base_url}/api/v1/internal/credentials/{credential_id}/token"
        params = {}
        if oauth_provider:
            params["oauth_provider"] = oauth_provider

        headers = {"X-Worker-Secret": self.worker_secret, "Accept": "application/json"}

        try:
            client = self._get_async_client()
            response = await client.get(
                url, headers=headers, params=params, timeout=settings.HTTP_INTERNAL_TIMEOUT_S
            )

            if response.status_code == 200:
                data = response.json()
                access_token = data.get("access_token")
                if access_token:
                    self._evict_cache_if_full()
                    self._token_cache[credential_id] = (
                        access_token,
                        time.monotonic() + _TOKEN_CACHE_TTL_S,
                    )
                logger.debug(
                    f"Fetched fresh token for credential {credential_id[:8]}..."
                )
                return access_token
            else:
                logger.error(
                    f"Token fetch failed: {response.status_code} - {' '.join(response.text.split())[:120]}"
                )
                return None

        except httpx.RequestError as e:
            logger.error(f"Token fetch network error: {e}")
            return None

    async def get_credential(self, credential_id: str) -> Optional[dict]:
        """Fetch full credential data for non-token auth types."""
        if not self.worker_secret:
            logger.error("Cannot fetch credential: WORKER_SHARED_SECRET not configured")
            return None

        url = f"{self.api_base_url}/api/v1/internal/credentials/{credential_id}"

        headers = {"X-Worker-Secret": self.worker_secret, "Accept": "application/json"}

        try:
            client = self._get_async_client()
            response = await client.get(url, headers=headers, timeout=settings.HTTP_INTERNAL_TIMEOUT_S)

            if response.status_code == 200:
                data = response.json()
                logger.debug(f"Fetched credential {credential_id[:8]}...")
                return data.get("credentials")
            else:
                logger.error(
                    f"Credential fetch failed: {response.status_code} - {' '.join(response.text.split())[:120]}"
                )
                return None

        except httpx.RequestError as e:
            logger.error(f"Credential fetch network error: {e}")
            return None

    def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create the reusable async HTTP client."""
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(timeout=settings.HTTP_INTERNAL_TIMEOUT_S)
        return self._async_client

    def _evict_cache_if_full(self) -> None:
        """Evict expired entries; if still over max size, drop oldest."""
        now = time.monotonic()
        # First pass: remove expired
        expired = [k for k, (_, exp) in self._token_cache.items() if exp <= now]
        for k in expired:
            del self._token_cache[k]
        # Second pass: if still over limit, drop oldest by expiry
        if len(self._token_cache) >= _TOKEN_CACHE_MAX_SIZE:
            oldest = sorted(self._token_cache, key=lambda k: self._token_cache[k][1])
            for k in oldest[: len(self._token_cache) - _TOKEN_CACHE_MAX_SIZE + 1]:
                del self._token_cache[k]

    async def close(self) -> None:
        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()
