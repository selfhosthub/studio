# api/app/infrastructure/adapters/webhook_adapter.py

"""Webhook adapter - outbound HTTP calls with Jinja2-templated parameters."""

import logging
from typing import Any, Dict, Optional
from uuid import UUID
import httpx
from jinja2 import Template, TemplateError

from app.application.interfaces.provider_adapter import (
    ProviderExecutionResult,
    CredentialValidationResult,
    HealthCheckResult,
)
from app.config.settings import settings
from app.infrastructure.adapters.base_adapter import BaseProviderAdapter
from app.infrastructure.errors import safe_error_message

logger = logging.getLogger(__name__)


class WebhookAdapter(BaseProviderAdapter):
    """Built-in adapter for webhook step types - outbound HTTP without a full provider integration."""

    def __init__(self):
        # Placeholder base URL - webhooks specify their own URLs per request.
        super().__init__(
            base_url="https://webhook.internal",
            timeout_seconds=settings.WEBHOOK_TIMEOUT,
            max_retries=settings.JOB_RETRY_LIMIT,
        )

    @property
    def provider_name(self) -> str:
        return "webhook"

    @property
    def supported_services(self) -> list[str]:
        return ["webhook.http", "webhook.outbound"]

    def supports_service(self, service_id: str) -> bool:
        return service_id in self.supported_services

    async def execute_service(
        self,
        service_id: str,
        parameters: Dict[str, Any],
        credentials: Dict[str, Any],
        organization_id: UUID,
        timeout_seconds: Optional[int] = None,
        service_config: Optional[Dict[str, Any]] = None,
    ) -> ProviderExecutionResult:
        if not self.supports_service(service_id):
            return ProviderExecutionResult(
                success=False,
                error=f"Unsupported service: {service_id}",
            )

        url_template = parameters.get("url")
        method = parameters.get("method", "POST").upper()
        headers_template = parameters.get("headers", {})
        body_template = parameters.get("body")
        query_params = parameters.get("query_params", {})
        timeout = timeout_seconds or parameters.get(
            "timeout_seconds", settings.WEBHOOK_TIMEOUT
        )

        if not url_template:
            return ProviderExecutionResult(
                success=False,
                error="Missing required parameter: url",
            )

        valid_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
        if method not in valid_methods:
            return ProviderExecutionResult(
                success=False,
                error=f"Invalid HTTP method: {method}. Must be one of {valid_methods}",
            )

        # SECURITY: never log secrets_dict.
        secrets_dict = {}
        try:
            from app.infrastructure.repositories.organization_secret_repository import (
                SQLAlchemyOrganizationSecretRepository,
            )
            from app.infrastructure.persistence.database import get_db_session

            async for session in get_db_session():
                secret_repo = SQLAlchemyOrganizationSecretRepository(session)
                org_secrets = await secret_repo.list_by_organization(
                    organization_id=organization_id,
                    include_inactive=False,
                )
                secrets_dict = {s.name: s.secret_data for s in org_secrets}
                break
        except Exception as e:
            # Non-fatal - proceed without secrets.
            logger.warning(f"Failed to load organization secrets: {e}")

        # SECURITY: never log this context - it contains credentials and secrets.
        context = {
            "credentials": credentials,
            "secrets": secrets_dict,
            "organization_id": str(organization_id),
            **parameters.get("template_context", {}),
        }

        try:
            url = self._render_template(url_template, context)

            headers = {}
            for key, value in headers_template.items():
                headers[key] = self._render_template(str(value), context)

            if (
                body_template is not None
                and "Content-Type" not in headers
                and "content-type" not in headers
            ):
                headers["Content-Type"] = "application/json"

            body = None
            if body_template is not None:
                if isinstance(body_template, dict):
                    body = {}
                    for key, value in body_template.items():
                        if isinstance(value, str):
                            body[key] = self._render_template(value, context)
                        else:
                            body[key] = value
                elif isinstance(body_template, str):
                    body = self._render_template(body_template, context)
                else:
                    body = body_template

            logger.info(
                f"Webhook request: {method} {url}",
                extra={
                    "method": method,
                    "url": url,
                    "service_id": service_id,
                    "organization_id": str(organization_id),
                },
            )

            import time

            start_time = time.time()

            response = await self._request_with_retry(
                method=method,
                url=url,
                headers=headers,
                json=body if isinstance(body, dict) else None,
                params=query_params,
                timeout=float(timeout),
            )

            execution_time_ms = int((time.time() - start_time) * 1000)

            if 200 <= response.status_code < 300:
                try:
                    response_data = response.json()
                except ValueError:
                    response_data = {"response": response.text}

                logger.info(
                    f"Webhook request succeeded: {method} {url} ({response.status_code})",
                    extra={
                        "status_code": response.status_code,
                        "execution_time_ms": execution_time_ms,
                    },
                )

                return ProviderExecutionResult(
                    success=True,
                    data={
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "body": response_data,
                    },
                    execution_time_ms=execution_time_ms,
                    provider_request_id=response.headers.get("X-Request-ID"),
                    metadata={
                        "url": url,
                        "method": method,
                    },
                )
            else:
                error_message = f"HTTP {response.status_code}: {response.text[:500]}"
                logger.warning(
                    f"Webhook request failed: {method} {url} ({response.status_code})",
                    extra={
                        "status_code": response.status_code,
                        "error": error_message,
                    },
                )

                return ProviderExecutionResult(
                    success=False,
                    error=error_message,
                    execution_time_ms=execution_time_ms,
                    data={
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "body": response.text,
                    },
                )

        except TemplateError:
            logger.exception("Template rendering error")
            return ProviderExecutionResult(
                success=False,
                error="Template rendering error. See server logs for details.",
            )
        except httpx.TimeoutException:
            logger.exception("Webhook request timeout")
            return ProviderExecutionResult(
                success=False,
                error=f"Request timeout after {timeout}s",
            )
        except httpx.HTTPError as e:
            logger.exception("Webhook HTTP error")
            return ProviderExecutionResult(
                success=False,
                error=safe_error_message(e),
            )
        except Exception as e:
            logger.exception("Webhook execution error")
            return ProviderExecutionResult(
                success=False,
                error=safe_error_message(e),
            )

    def _render_template(self, template_str: str, context: Dict[str, Any]) -> str:
        template = Template(template_str)
        return template.render(**context)  # nosemgrep - JSON payload, not HTML

    async def validate_credentials(
        self,
        credentials: Dict[str, Any],
    ) -> CredentialValidationResult:
        # Webhooks have no credentials to validate up front; templates resolve at runtime.
        return CredentialValidationResult(
            valid=True,
            metadata={"note": "Webhook credentials validated at runtime"},
        )

    async def health_check(self) -> HealthCheckResult:
        # No upstream to ping - webhook URLs are per-request.
        return HealthCheckResult(
            healthy=True,
            latency_ms=0,
            details={"message": "Webhook adapter ready"},
        )

    def get_service_schema(self, service_id: str) -> Dict[str, Any]:
        if not self.supports_service(service_id):
            return {}

        return {
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Target URL (supports Jinja2 templating)",
                    "example": "https://api.example.com/webhook",
                },
                "method": {
                    "type": "string",
                    "enum": [
                        "GET",
                        "POST",
                        "PUT",
                        "DELETE",
                        "PATCH",
                        "HEAD",
                        "OPTIONS",
                    ],
                    "default": "POST",
                    "description": "HTTP method",
                },
                "headers": {
                    "type": "object",
                    "description": "HTTP headers (supports Jinja2 templating in values)",
                    "example": {
                        "Content-Type": "application/json",
                        "Authorization": "Bearer {{ credentials.api_key }}",
                    },
                },
                "body": {
                    "type": ["object", "string", "null"],
                    "description": "Request body (supports Jinja2 templating)",
                    "example": {
                        "event": "workflow_completed",
                        "workflow_id": "{{ workflow_id }}",
                    },
                },
                "query_params": {
                    "type": "object",
                    "description": "URL query parameters",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "default": 30,
                    "description": "Request timeout in seconds",
                },
                "template_context": {
                    "type": "object",
                    "description": "Additional variables for template rendering",
                },
            },
        }
