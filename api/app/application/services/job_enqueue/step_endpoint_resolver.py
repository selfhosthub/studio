# api/app/application/services/job_enqueue/step_endpoint_resolver.py

"""
Step endpoint and credential resolution.

Resolves provider base URL, service endpoint path, HTTP method, auth config,
and credentials for a workflow step.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.domain.organization.repository import OrganizationRepository
from app.domain.provider.models import Provider, ProviderStatus
from app.domain.common.exceptions import BusinessRuleViolation
from app.domain.provider.repository import (
    ProviderCredentialRepository,
    ProviderRepository,
    ProviderServiceRepository,
)

logger = logging.getLogger(__name__)

# HTTP method suffix patterns in service IDs (e.g., "provider.http.get")
HTTP_METHOD_SUFFIXES = {
    ".get": "GET",
    ".put": "PUT",
    ".delete": "DELETE",
    ".patch": "PATCH",
}


class ProviderInactiveError(BusinessRuleViolation):
    """Raised when a provider is inactive and cannot be used."""

    pass


class ServiceInactiveError(BusinessRuleViolation):
    """Raised when a service is inactive and cannot be used."""

    pass


class EmptyIterationSourceError(BusinessRuleViolation):
    """Raised when an iteration step's source array resolved to an empty list.

    The action executor catches this and fails the step and instance immediately
    so the operator sees the upstream gap without waiting for the stale-step sweep.
    """

    def __init__(self, step_id: str, source_step: str, source_field: str):
        self.step_id = step_id
        self.source_step = source_step
        self.source_field = source_field
        super().__init__(
            f"Step '{step_id}': iteration source '{source_step}.{source_field}' "
            f"is empty. Upstream step produced no items to iterate over."
        )


@dataclass
class ResolvedEndpoint:
    """Result of resolving a step's endpoint configuration.

    Contains all information needed to make the HTTP request to the provider API.
    """

    url: Optional[str] = None
    http_method: str = "POST"
    post_processing: Optional[Dict[str, Any]] = None
    polling: Optional[Dict[str, Any]] = None
    auth_config: Optional[Dict[str, Any]] = None
    local_worker: Optional[Dict[str, Any]] = None
    parameter_mapping: Optional[Dict[str, Any]] = None
    default_headers: Optional[Dict[str, str]] = None
    service_metadata: Optional[Dict[str, Any]] = None
    parameter_schema: Optional[Dict[str, Any]] = None
    result_schema: Optional[Dict[str, Any]] = None
    provider_default_queue: Optional[str] = None
    # Declarative reshape for producing the wire body / query params.
    # request_body_template is a deprecated alias normalized into request_transform.body.
    request_transform: Optional[Dict[str, Any]] = None
    # Raw service endpoint path (pre-URL-substitution).
    # The fully-rendered URL is in url above; this is the unrendered source.
    service_endpoint_path: Optional[str] = None
    # Provider config for HTTP adapter construction. Set only for HTTP-provider paths
    # (not local_worker / direct-URL / provider-not-found).
    provider_adapter_config: Optional[Dict[str, Any]] = None
    # Worker-side handler-selector list. Routes dispatch-declaring core services
    # through a generic outbound-HTTP handler. None for non-core providers.
    dispatch: Optional[list] = None


def extract_http_method_from_service_id(service_id: Optional[str]) -> str:
    """Extract HTTP method from service_id naming convention.

    Checks for method suffixes like .get, .put, .delete, .patch.
    Falls back to POST if no method suffix is found.
    """
    if not service_id:
        return "POST"

    service_id_lower = service_id.lower()
    for suffix, method in HTTP_METHOD_SUFFIXES.items():
        if suffix in service_id_lower:
            return method
    return "POST"


class StepEndpointResolver:
    """Resolves endpoint URL, credentials, and org settings for a step."""

    def __init__(
        self,
        credential_repository: ProviderCredentialRepository,
        provider_repository: ProviderRepository,
        provider_service_repository: ProviderServiceRepository,
        organization_repository: Optional[OrganizationRepository] = None,
    ):
        self.credential_repository = credential_repository
        self.provider_repository = provider_repository
        self.provider_service_repository = provider_service_repository
        self.organization_repository = organization_repository

    async def _resolve_provider(self, provider_id_str: str) -> Optional[Provider]:
        """Resolve a provider by UUID or slug."""
        try:
            provider_id = uuid.UUID(provider_id_str)
            return await self.provider_repository.get_by_id(provider_id)
        except (ValueError, AttributeError):
            return await self.provider_repository.get_by_slug(provider_id_str)

    async def resolve_step_credential(
        self, step_config: Dict[str, Any], organization_id: uuid.UUID
    ) -> Optional[str]:
        """Resolve credential ID for a step: explicit selection first, then default."""
        job = step_config.get("job") or {}

        # Check for explicitly set credential_id first (cross-provider or user-selected)
        explicit_credential_id = job.get("credential_id")
        if explicit_credential_id:
            return str(explicit_credential_id)

        # Fall back to default credential for the step's provider
        # Step level takes precedence over job level.
        provider_id_str = step_config.get("provider_id") or job.get("provider_id")
        if not provider_id_str:
            return None

        try:
            provider = await self._resolve_provider(provider_id_str)
            if not provider:
                return None
            credential = await self.credential_repository.get_default_credential(
                provider_id=provider.id, organization_id=organization_id
            )
            return str(credential.id) if credential else None
        except Exception as e:
            # Log so credential fetch errors don't silently become "no credential."
            # A DB or network error here would otherwise look like no default credential exists.
            logger.warning(
                f"Default credential lookup failed for provider {provider_id_str}: {e}"
            )
            return None

    async def resolve_step_endpoint(
        self, step_config: Dict[str, Any]
    ) -> ResolvedEndpoint:
        """Resolve the full endpoint for a step.

        Resolution order:
        1. Direct URL from step parameters - for core HTTP services
        2. Provider base URL + service endpoint path - for external providers

        Raises:
            ProviderInactiveError: If the provider is inactive.
            ServiceInactiveError: If the service is inactive.
        """
        job = step_config.get("job") or {}

        # Step level takes precedence over job level.
        provider_id_str = step_config.get("provider_id") or job.get("provider_id")
        service_id_str = step_config.get("service_id") or job.get("service_id")

        if not provider_id_str or not service_id_str:
            return ResolvedEndpoint()

        # Check for direct URL in parameters
        parameters = job.get("parameters") or {}
        direct_url = parameters.get("url")

        try:
            provider = await self._resolve_provider(provider_id_str)

            # If provider not found, use direct URL from parameters
            if not provider:
                if direct_url:
                    http_method = extract_http_method_from_service_id(service_id_str)
                    return ResolvedEndpoint(url=direct_url, http_method=http_method)
                return ResolvedEndpoint()

            # Check for local_worker config (for shs-* providers with no endpoint_url)
            local_worker = (
                provider.config.get("local_worker") if provider.config else None
            )
            if local_worker and local_worker.get("enabled"):
                # Local worker provider - return early with local_worker config
                auth_config = provider.config.get("auth") if provider.config else None
                return ResolvedEndpoint(
                    auth_config=auth_config, local_worker=local_worker
                )

            # Check if provider is active
            if provider.status == ProviderStatus.INACTIVE:
                raise ProviderInactiveError(
                    f"Provider '{provider.name}' is currently inactive"
                )

            # Get service for endpoint path and method
            service = await self.provider_service_repository.get_by_service_id(
                service_id=service_id_str,
                skip=0,
                limit=1,
            )

            if not service:
                # Service not found - use provider base URL or direct URL from parameters
                auth_config = provider.config.get("auth") if provider.config else None
                local_worker = (
                    provider.config.get("local_worker") if provider.config else None
                )
                url = provider.endpoint_url or direct_url
                http_method = (
                    extract_http_method_from_service_id(service_id_str)
                    if not provider.endpoint_url
                    else "POST"
                )
                return ResolvedEndpoint(
                    url=url,
                    http_method=http_method,
                    auth_config=auth_config,
                    local_worker=local_worker,
                )

            # Check if service is active
            if not service.is_active:
                raise ServiceInactiveError(
                    f"Service '{service.display_name}' ({service.service_id}) is currently inactive"
                )

            # Build full URL
            # Use service-specific endpoint_url if present, otherwise provider's base URL
            service_endpoint_url = (
                service.client_metadata.get("endpoint_url")
                if service.client_metadata
                else None
            )
            base_url = (service_endpoint_url or provider.endpoint_url or "").rstrip("/")
            endpoint_path = service.endpoint or ""

            if endpoint_path and not endpoint_path.startswith("/"):
                endpoint_path = "/" + endpoint_path

            full_url = base_url + endpoint_path

            # Substitute parameters in URL
            job_config = step_config.get("job", {})
            parameters = job_config.get("parameters", {})
            if parameters and "{" in full_url:
                # Jinja2-style: {{ parameters.upload_url }} -> resolved param value
                # Used when the entire URL comes from a parameter (e.g., YouTube resumable upload)
                def substitute_jinja_param(match: re.Match[str]) -> str:
                    param_name = match.group(1)
                    value = parameters.get(param_name)
                    if value is not None:
                        return str(value)
                    return match.group(0)

                full_url = re.sub(
                    r"\{\{\s*parameters\.(\w+)\s*\}\}",
                    substitute_jinja_param,
                    full_url,
                )

                # REST path params: {base_id} -> actual value
                def substitute_path_param(match: re.Match[str]) -> str:
                    param_name = match.group(1)
                    value = parameters.get(param_name)
                    if value is not None:
                        return str(value)
                    return match.group(0)  # Keep original if no value

                full_url = re.sub(
                    r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", substitute_path_param, full_url
                )

            # Get HTTP method from service config (default POST)
            http_method = "POST"
            if service.client_metadata:
                http_method = service.client_metadata.get("method", "POST")

            # Get post_processing config from service (for worker to handle file downloads, etc.)
            post_processing = None
            if service.client_metadata:
                post_processing = service.client_metadata.get("post_processing")

            # Get polling config from service (for async provider APIs)
            polling = None
            if service.client_metadata:
                polling = service.client_metadata.get("polling")

            # Get auth config from provider (for custom auth headers like x-api-key)
            auth_config = provider.config.get("auth") if provider.config else None

            # Get default_headers from provider's adapter_config (e.g., Notion-Version)
            default_headers = None
            if provider.config:
                adapter_config = provider.config.get("adapter_config", {})
                default_headers = adapter_config.get("default_headers")

            # Get local_worker config from provider (for shs-* self-hosted providers)
            local_worker = (
                provider.config.get("local_worker") if provider.config else None
            )

            # Get parameter_mapping from service (explicit mapping of params to path/query/body)
            parameter_mapping = None
            if service.client_metadata:
                parameter_mapping = service.client_metadata.get("parameter_mapping")

            # Service-level request_transform - canonical declarative reshape of
            # form params → wire body / query_params. Fall back to the deprecated
            # request_body_template alias, wrapped as {"body": <contents>}.
            request_transform = None
            if service.client_metadata:
                request_transform = service.client_metadata.get("request_transform")
                if request_transform is None:
                    legacy_body_template = service.client_metadata.get(
                        "request_body_template"
                    )
                    if legacy_body_template:
                        request_transform = {"body": legacy_body_template}

            # Get provider-level default_queue (from adapter-config.default_queue)
            provider_default_queue = None
            if provider.config:
                adapter_config = provider.config.get("adapter_config", {})
                provider_default_queue = adapter_config.get("default_queue")

            # Provider config in the shape GenericHTTPAdapter wants. Carried
            # through so the enqueue service can instantiate a transient
            # adapter and build the wire envelope.
            from app.infrastructure.adapters.provider_loader import (
                build_adapter_provider_config,
            )

            provider_adapter_config = build_adapter_provider_config(provider)

            dispatch = None
            if service.client_metadata:
                raw_dispatch = service.client_metadata.get("dispatch")
                if isinstance(raw_dispatch, list):
                    dispatch = raw_dispatch

            return ResolvedEndpoint(
                url=full_url,
                http_method=http_method,
                post_processing=post_processing,
                polling=polling,
                auth_config=auth_config,
                local_worker=local_worker,
                parameter_mapping=parameter_mapping,
                default_headers=default_headers,
                service_metadata=service.client_metadata,
                parameter_schema=service.parameter_schema,
                result_schema=service.result_schema,
                provider_default_queue=provider_default_queue,
                request_transform=request_transform,
                service_endpoint_path=service.endpoint,
                provider_adapter_config=provider_adapter_config,
                dispatch=dispatch,
            )

        except (ProviderInactiveError, ServiceInactiveError):
            # Re-raise these specific errors to be handled by caller
            raise
        except Exception as e:
            logger.error(f"Failed to resolve endpoint for step: {e}")
            return ResolvedEndpoint()

    async def get_org_settings(self, organization_id: uuid.UUID) -> Dict[str, Any]:
        """Return organization settings relevant to the worker.

        Currently extracts generate_thumbnails (defaults to True if not configured).
        """
        # Default worker-relevant settings
        worker_settings: Dict[str, Any] = {
            "generate_thumbnails": True,  # Default: generate thumbnails
        }

        if not self.organization_repository:
            return worker_settings

        try:
            org = await self.organization_repository.get_by_id(organization_id)
            if org and org.settings:
                # Get general settings (where generate_thumbnails lives)
                general_settings = org.settings.get("general", {})

                # Override defaults with org settings if present
                if "generate_thumbnails" in general_settings:
                    worker_settings["generate_thumbnails"] = general_settings[
                        "generate_thumbnails"
                    ]

            return worker_settings
        except Exception:
            # If we can't fetch org settings, use defaults
            return worker_settings
