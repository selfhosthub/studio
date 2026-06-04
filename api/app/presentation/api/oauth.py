# api/app/presentation/api/oauth.py

"""OAuth2 endpoints. Two modes: platform (env-var creds, preferred) and org-managed (own client_id/secret).

Security: state has CSRF protection + TTL; tokens encrypted at rest; credentials are org-scoped.
"""

import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, UTC
from typing import Any, Dict, Optional
from urllib.parse import urlencode, urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel


def _build_oauth_redirect_url(frontend_url: str, params: Dict[str, str]) -> str:
    """Validates scheme http/https; URL-encodes params to prevent injection."""
    parsed = urlparse(frontend_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid frontend URL scheme: {parsed.scheme}")
    if not parsed.netloc:
        raise ValueError("Invalid frontend URL: missing host")

    query_string = urlencode(params)
    return f"{frontend_url}/providers?{query_string}"


from app.domain.provider.models import CredentialType, ProviderCredential
from app.domain.provider.repository import (
    ProviderCredentialRepository,
    ProviderRepository,
)
from app.infrastructure.auth.jwt import get_current_user
from app.infrastructure.security.oauth_state import set_state, get_state, delete_state
from app.presentation.api.dependencies import (
    CurrentUser,
    get_provider_credential_repository,
    get_provider_credential_repository_bypass,
    get_provider_repository,
    get_provider_repository_bypass,
    require_admin,
)
from app.config.settings import settings
from app.presentation.api.oauth_config import (
    get_all_oauth_configs,
    get_oauth_config_from_provider,
    get_platform_credentials,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["OAuth"])


class OAuthAuthorizeResponse(BaseModel):
    """Response containing the OAuth authorization URL."""

    authorization_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    """Request model for OAuth callback."""

    code: str
    state: str


class OAuthTokenResponse(BaseModel):
    """Response model for OAuth token operations."""

    credential_id: str
    provider: str
    expires_at: Optional[datetime] = None
    message: str


def get_redirect_uri(provider: str) -> str:
    """Full OAuth callback URL. Raises if API_BASE_URL is unset."""
    base_url = settings.API_BASE_URL
    if not base_url:
        raise RuntimeError("API_BASE_URL is required and not set")
    return f"{base_url}/api/v1/oauth/{provider}/callback"


@router.get("/{provider}/authorize", response_model=OAuthAuthorizeResponse)
async def oauth_authorize(
    provider: str,
    credential_id: Optional[str] = Query(
        None, description="Credential ID (org-managed OAuth)"
    ),
    provider_id: Optional[str] = Query(
        None, description="Provider ID (platform OAuth - no credential needed)"
    ),
    reauth_credential_id: Optional[str] = Query(
        None, description="Existing credential to re-authorize (platform OAuth)"
    ),
    user: CurrentUser = Depends(require_admin),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    credential_repo: ProviderCredentialRepository = Depends(
        get_provider_credential_repository
    ),
) -> OAuthAuthorizeResponse:
    """Start OAuth flow. Modes: platform (provider_id), org-managed (credential_id), reauth (reauth_credential_id+provider_id)."""
    platform_oauth = credential_id is None

    if platform_oauth:
        if not provider_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="provider_id is required for platform OAuth",
            )
        resolved_provider_id = provider_id
        oauth_config = await get_oauth_config_from_provider(
            UUID(provider_id), provider_repo
        )
        client_id, client_secret = get_platform_credentials(oauth_config)
        if not client_id or not client_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Platform OAuth not configured for {provider}. "
                f"Set {oauth_config.get('client_id_env', '')} and "
                f"{oauth_config.get('client_secret_env', '')} environment variables.",
            )
    else:
        credential = await credential_repo.get_by_id(UUID(credential_id))

        if not credential:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Credential not found",
            )

        if str(credential.organization_id) != user["org_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this credential",
            )

        client_id = credential.credentials.get("client_id")
        client_secret = credential.credentials.get("client_secret")

        if not client_id or not client_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Credential must have client_id and client_secret populated before OAuth authorization",
            )

        resolved_provider_id = str(credential.provider_id)
        oauth_config = await get_oauth_config_from_provider(
            credential.provider_id, provider_repo
        )

    # Generate secure state token
    state = secrets.token_urlsafe(32)

    # Generate PKCE code_verifier/code_challenge (always - improves security for all providers)
    code_verifier = secrets.token_urlsafe(64)  # 86 chars, well within 43-128 range
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )

    # Store state in-memory with TTL
    state_data = {
        "user_id": user["id"],
        "org_id": user["org_id"],
        "provider": provider,
        "credential_id": credential_id,  # None for platform OAuth
        "provider_id": resolved_provider_id,
        "platform_oauth": platform_oauth,
        "reauth_credential_id": reauth_credential_id,  # Existing credential to update
        "created_at": datetime.now(UTC).isoformat(),
        "code_verifier": code_verifier,
    }

    await set_state(
        f"oauth_state:{state}",
        json.dumps(state_data),
        settings.OAUTH_STATE_EXPIRY,
    )

    # Build authorization URL from provider's DB config
    redirect_uri = get_redirect_uri(provider)
    scope_delimiter = oauth_config.get("scope_delimiter", " ")
    scopes = scope_delimiter.join(oauth_config.get("scopes", []))
    client_id_param = oauth_config.get("client_id_param", "client_id")

    params = {
        client_id_param: client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
        "state": state,
    }

    # Add PKCE challenge
    params["code_challenge"] = code_challenge
    params["code_challenge_method"] = "S256"

    # Add provider-specific auth params (e.g. Google needs access_type, prompt)
    # Defaults to Google-compatible params for backwards compatibility
    auth_params = oauth_config.get(
        "auth_params",
        {
            "access_type": "offline",
            "prompt": "consent select_account",
        },
    )
    params.update(auth_params)

    authorization_url = f"{oauth_config['authorization_url']}?{urlencode(params)}"

    mode = "platform" if platform_oauth else f"credential {credential_id}"
    logger.info(
        f"OAuth authorization started for provider {provider} by user {user['id']} "
        f"using {mode}"
    )

    return OAuthAuthorizeResponse(
        authorization_url=authorization_url,
        state=state,
    )


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str = Query(..., description="Authorization code from provider"),
    state: str = Query(..., description="State token for CSRF protection"),
    error: Optional[str] = Query(None, description="Error from provider"),
    error_description: Optional[str] = Query(None, description="Error description"),
    provider_repo: ProviderRepository = Depends(get_provider_repository_bypass),
    credential_repo: ProviderCredentialRepository = Depends(
        get_provider_credential_repository_bypass
    ),
) -> RedirectResponse:
    """OAuth provider callback. Exchanges code for tokens, persists, redirects to frontend."""
    import httpx

    frontend_url = settings.FRONTEND_URL
    if not frontend_url:
        raise RuntimeError("FRONTEND_URL is required and not set")

    if error:
        logger.error(f"OAuth error from {provider}: {error} - {error_description}")
        return RedirectResponse(
            url=_build_oauth_redirect_url(
                frontend_url, {"oauth_error": error, "provider": provider}
            ),
            status_code=status.HTTP_302_FOUND,
        )

    state_data_raw = await get_state(f"oauth_state:{state}")

    if not state_data_raw:
        logger.warning(f"Invalid or expired OAuth state: {state[:8]}...")
        return RedirectResponse(
            url=_build_oauth_redirect_url(
                frontend_url, {"oauth_error": "invalid_state", "provider": provider}
            ),
            status_code=status.HTTP_302_FOUND,
        )

    try:
        state_data = json.loads(state_data_raw)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OAuth state data: {e}")
        return RedirectResponse(
            url=_build_oauth_redirect_url(
                frontend_url, {"oauth_error": "invalid_state", "provider": provider}
            ),
            status_code=status.HTTP_302_FOUND,
        )

    # State is single-use - delete before exchange
    await delete_state(f"oauth_state:{state}")

    platform_oauth = state_data.get("platform_oauth", False)

    provider_id_str = state_data.get("provider_id")
    if not provider_id_str:
        logger.error("No provider_id in OAuth state")
        return RedirectResponse(
            url=_build_oauth_redirect_url(
                frontend_url, {"oauth_error": "invalid_state", "provider": provider}
            ),
            status_code=status.HTTP_302_FOUND,
        )

    try:
        _provider_record = await provider_repo.get_by_id(UUID(provider_id_str))
        if not _provider_record or not _provider_record.config.get("oauth"):
            raise HTTPException(status_code=400, detail="no oauth config")
        oauth_config = _provider_record.config["oauth"]
        provider_name = _provider_record.name
    except HTTPException:
        return RedirectResponse(
            url=_build_oauth_redirect_url(
                frontend_url,
                {"oauth_error": "provider_not_supported", "provider": provider},
            ),
            status_code=status.HTTP_302_FOUND,
        )

    if platform_oauth:
        client_id, client_secret = get_platform_credentials(oauth_config)
        if not client_id or not client_secret:
            logger.error(
                f"Platform OAuth credentials removed since authorize for {provider}"
            )
            return RedirectResponse(
                url=_build_oauth_redirect_url(
                    frontend_url,
                    {"oauth_error": "platform_not_configured", "provider": provider},
                ),
                status_code=status.HTTP_302_FOUND,
            )
        credential = None
    else:
        credential_id = state_data.get("credential_id")
        if not credential_id:
            logger.error("No credential_id in OAuth state")
            return RedirectResponse(
                url=_build_oauth_redirect_url(
                    frontend_url, {"oauth_error": "invalid_state", "provider": provider}
                ),
                status_code=status.HTTP_302_FOUND,
            )

        credential = await credential_repo.get_by_id(UUID(credential_id))
        if not credential:
            logger.error(f"Credential {credential_id} not found during OAuth callback")
            return RedirectResponse(
                url=_build_oauth_redirect_url(
                    frontend_url,
                    {"oauth_error": "credential_not_found", "provider": provider},
                ),
                status_code=status.HTTP_302_FOUND,
            )

        client_id = credential.credentials.get("client_id")
        client_secret = credential.credentials.get("client_secret")

        if not client_id or not client_secret:
            logger.error(
                f"Credential {credential_id} missing client_id or client_secret"
            )
            return RedirectResponse(
                url=_build_oauth_redirect_url(
                    frontend_url,
                    {"oauth_error": "missing_client_credentials", "provider": provider},
                ),
                status_code=status.HTTP_302_FOUND,
            )

    redirect_uri = get_redirect_uri(provider)
    client_id_param = oauth_config.get("client_id_param", "client_id")

    token_request_data = {
        client_id_param: client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }

    # PKCE code_verifier (only present when PKCE was used at authorize)
    code_verifier = state_data.get("code_verifier")
    if code_verifier:
        token_request_data["code_verifier"] = code_verifier

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
                    f"Token exchange failed with status {response.status_code}"
                )
                return RedirectResponse(
                    url=_build_oauth_redirect_url(
                        frontend_url,
                        {"oauth_error": "token_exchange_failed", "provider": provider},
                    ),
                    status_code=status.HTTP_302_FOUND,
                )

            tokens = response.json()
    except Exception as e:
        logger.error(f"Token exchange error: {e}")
        return RedirectResponse(
            url=_build_oauth_redirect_url(
                frontend_url,
                {"oauth_error": "token_exchange_error", "provider": provider},
            ),
            status_code=status.HTTP_302_FOUND,
        )

    expires_at = None
    if "expires_in" in tokens:
        expires_at = datetime.now(UTC) + timedelta(seconds=tokens["expires_in"])

    try:
        if platform_oauth:
            reauth_id = state_data.get("reauth_credential_id")

            if reauth_id:
                existing_cred = await credential_repo.get_by_id(UUID(reauth_id))
                if existing_cred:
                    existing_cred.credentials = {
                        "access_token": tokens.get("access_token"),
                        "refresh_token": tokens.get("refresh_token"),
                        "token_type": tokens.get("token_type", "Bearer"),
                        "scope": tokens.get("scope"),
                    }
                    existing_cred.is_active = True
                    existing_cred.expires_at = expires_at
                    existing_cred.updated_at = datetime.now(UTC)
                    await credential_repo.update(existing_cred)
                    logger.info(
                        f"Platform OAuth credential {reauth_id} re-authorized for "
                        f"provider {provider}, org {state_data['org_id']}"
                    )
                else:
                    logger.warning(
                        f"Re-auth credential {reauth_id} not found, creating new"
                    )
                    reauth_id = None  # fall through to create

            if not reauth_id:
                # Platform OAuth credential stores tokens only - no client_id/secret
                import uuid as uuid_mod

                new_credential = ProviderCredential(
                    id=uuid_mod.uuid4(),
                    provider_id=UUID(state_data["provider_id"]),
                    organization_id=UUID(state_data["org_id"]),
                    credential_type=CredentialType.OAUTH2,
                    name=f"{provider_name} OAuth",
                    credentials={
                        "access_token": tokens.get("access_token"),
                        "refresh_token": tokens.get("refresh_token"),
                        "token_type": tokens.get("token_type", "Bearer"),
                        "scope": tokens.get("scope"),
                    },
                    is_active=True,
                    is_token_type=True,
                    expires_at=expires_at,
                    created_by=UUID(state_data["user_id"]),
                )
                await credential_repo.create(new_credential)
                logger.info(
                    f"Platform OAuth credential created for provider {provider}, "
                    f"org {state_data['org_id']}"
                )
        else:
            # Org-managed: preserve client_id/client_secret on the credential
            assert credential is not None  # guaranteed by earlier branch
            credential.credentials = {
                "client_id": client_id,
                "client_secret": client_secret,
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "token_type": tokens.get("token_type", "Bearer"),
                "scope": tokens.get("scope"),
            }
            credential.credential_type = CredentialType.OAUTH2
            credential.is_active = True
            credential.expires_at = expires_at
            credential.updated_at = datetime.now(UTC)

            await credential_repo.update(credential)
            logger.info(
                f"OAuth tokens stored in credential {state_data.get('credential_id')} "
                f"for provider {provider}, org {state_data['org_id']}"
            )
    except Exception as e:
        logger.error(f"Failed to save credential with tokens: {e}")
        return RedirectResponse(
            url=_build_oauth_redirect_url(
                frontend_url,
                {"oauth_error": "credential_update_failed", "provider": provider},
            ),
            status_code=status.HTTP_302_FOUND,
        )

    return RedirectResponse(
        url=f"{frontend_url}/providers/{state_data['provider_id']}/credentials?oauth_success=true",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/{provider}/refresh/{credential_id}", response_model=OAuthTokenResponse)
async def oauth_refresh(
    provider: str,
    credential_id: str,
    user: CurrentUser = Depends(require_admin),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    credential_repo: ProviderCredentialRepository = Depends(
        get_provider_credential_repository
    ),
) -> OAuthTokenResponse:
    """Refresh OAuth tokens. 403 cross-tenant; 400 wrong type or no refresh token; 503 provider unreachable."""
    import httpx

    credential = await credential_repo.get_by_id(UUID(credential_id))

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
        )

    # Multi-tenant: cross-org credential access is denied
    if str(credential.organization_id) != user["org_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this credential",
        )

    if credential.credential_type != CredentialType.OAUTH2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credential is not an OAuth2 credential",
        )

    oauth_config = await get_oauth_config_from_provider(
        credential.provider_id, provider_repo
    )

    client_id = credential.credentials.get("client_id")
    client_secret = credential.credentials.get("client_secret")
    refresh_token = credential.credentials.get("refresh_token")
    is_platform_credential = not client_id or not client_secret

    if is_platform_credential:
        client_id, client_secret = get_platform_credentials(oauth_config)
        if not client_id or not client_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Platform OAuth not configured for {provider}. "
                f"Cannot refresh platform-managed credential without env vars.",
            )

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No refresh token available. Re-authorize the application.",
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
                logger.error(f"Token refresh failed with status {response.status_code}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Token refresh failed. You may need to re-authorize.",
                )

            tokens = response.json()
    except httpx.RequestError as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to connect to OAuth provider",
        )

    expires_at = None
    if "expires_in" in tokens:
        expires_at = datetime.now(UTC) + timedelta(seconds=tokens["expires_in"])

    if is_platform_credential:
        # Platform-managed credential stores tokens only
        credential.credentials = {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token", refresh_token),
            "token_type": tokens.get("token_type", "Bearer"),
            "scope": tokens.get("scope", credential.credentials.get("scope")),
        }
    else:
        # Org-managed: preserve client_id/client_secret
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

    logger.info(f"OAuth tokens refreshed for credential {credential_id}")

    return OAuthTokenResponse(
        credential_id=str(credential.id),
        provider=provider,
        expires_at=expires_at,
        message="Tokens refreshed successfully",
    )


@router.get("/providers")
async def list_oauth_providers(
    user: CurrentUser = Depends(get_current_user),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
) -> Dict[str, Any]:
    """Returns providers grouped by oauth_provider with merged scopes and platform_configured flag."""
    configs = await get_all_oauth_configs(provider_repo)
    providers = {}

    for provider_name, oauth_config in configs.items():
        platform_id, _ = get_platform_credentials(oauth_config)
        providers[provider_name] = {
            "available": True,
            "scopes": oauth_config.get("scopes", []),
            "platform_configured": bool(platform_id),
        }

    return {"providers": providers}
