# api/app/infrastructure/adapters/generic_http_adapter.py

"""Generic HTTP adapter - request/response mapping driven by provider.adapter_config JSON."""

import logging
import re
import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional
from uuid import UUID
import jinja2
import jsonpath_ng
import httpx

# Whole-string Jinja expression: rendered value preserves native Python type
# (bool/number/list/dict) instead of being stringified.
_PURE_EXPR_RE = re.compile(r"^\s*\{\{\s*(.+?)\s*\}\}\s*$")

# Opt-in omit marker: fields rendering to this sentinel are stripped post-render.
# Preserves "" and None semantics where those values are meaningful.
OMIT_SENTINEL = "__omit__"


@dataclass
class BuiltRequest:
    """Credential-free HTTP request envelope. Auth is applied separately."""

    url: str
    method: str
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[Any] = None
    query_params: Dict[str, Any] = field(default_factory=dict)


from app.config.settings import settings
from app.infrastructure.adapters.base_adapter import BaseProviderAdapter
from app.infrastructure.errors import safe_error_message
from app.application.interfaces.provider_adapter import (
    ProviderExecutionResult,
    CredentialValidationResult,
    HealthCheckResult,
)

logger = logging.getLogger(__name__)


class GenericHTTPAdapter(BaseProviderAdapter):
    """Generic adapter for HTTP-based providers configured via JSON.

    Templates use Jinja2 with context keys: credentials, parameters, system.
    Response extraction uses JSONPath expressions.
    """

    def __init__(
        self,
        provider_config: Dict[str, Any],
        supported_services: Optional[list[str]] = None,
    ):
        self.config = provider_config
        self._provider_name = provider_config["name"]
        self._supported_services = supported_services or []

        base_url = provider_config.get("base_url", "")
        adapter_config = provider_config.get("adapter_config", {})

        error_config = adapter_config.get("error_config", {})
        max_retries = error_config.get("max_retries", settings.JOB_RETRY_LIMIT)

        super().__init__(
            base_url=base_url,
            timeout_seconds=settings.ADAPTER_CLIENT_TIMEOUT,
            max_retries=max_retries,
        )

        self.request_config = adapter_config.get("request_mapping", {})
        self.response_config = adapter_config.get("response_mapping", {})
        self.error_config = error_config
        self.webhook_config = provider_config.get("webhook_config", {})
        self.auth_config = adapter_config.get("auth", {})

        # JSON/API only - no HTML, no XSS risk. StrictUndefined surfaces missing vars.
        self.jinja_env = jinja2.Environment(  # nosemgrep
            autoescape=False,
            undefined=jinja2.StrictUndefined,
        )

        logger.info(
            f"GenericHTTPAdapter initialized for {self._provider_name} "
            f"(base_url={base_url})"
        )

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def supported_services(self) -> list[str]:
        return self._supported_services

    def supports_service(self, service_id: str) -> bool:
        # Service validation lives in the DB; adapter executes whatever is requested.
        return True

    async def execute_service(
        self,
        service_id: str,
        parameters: Dict[str, Any],
        credentials: Dict[str, Any],
        organization_id: UUID,
        timeout_seconds: Optional[int] = None,
        service_config: Optional[Dict[str, Any]] = None,
    ) -> ProviderExecutionResult:
        start_time = time.time()

        try:
            built = self.build_request(
                service_config=service_config,
                parameters=parameters,
                organization_id=organization_id,
                credentials=credentials,
            )
            built = self._apply_auth(built, credentials)

            response = await self._request_with_retry(
                method=built.method,
                url=built.url,
                headers=built.headers,
                json=built.body,
                params=built.query_params or None,
                timeout=timeout_seconds,
            )

            execution_time_ms = int((time.time() - start_time) * 1000)

            success_status = self.response_config.get("success_status", [200, 201])
            if response.status_code not in success_status:
                error_message = self._extract_error_message(response)
                return ProviderExecutionResult(
                    success=False,
                    error=f"HTTP {response.status_code}: {error_message}",
                    execution_time_ms=execution_time_ms,
                )

            response_data = response.json()
            extracted_data = self._extract_response_data(response_data)

            # Some APIs return arrays directly - guard the dict-only lookup.
            provider_request_id = (
                extracted_data.get("job_id")
                if isinstance(extracted_data, dict)
                else None
            )

            logger.info(
                f"Service {service_id} executed successfully "
                f"(provider_request_id={provider_request_id}, "
                f"execution_time={execution_time_ms}ms)"
            )

            return ProviderExecutionResult(
                success=True,
                data=extracted_data,
                execution_time_ms=execution_time_ms,
                provider_request_id=provider_request_id,
            )

        except jinja2.UndefinedError as e:
            logger.exception("Template rendering error")
            return ProviderExecutionResult(
                success=False,
                error=f"Configuration error: missing template variable. ({type(e).__name__})",
            )

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            logger.exception("Service execution failed")
            return ProviderExecutionResult(
                success=False,
                error=safe_error_message(e),
                execution_time_ms=execution_time_ms,
            )

    def build_request(
        self,
        service_config: Optional[Dict[str, Any]],
        parameters: Dict[str, Any],
        organization_id: UUID,
        credentials: Optional[Dict[str, Any]] = None,
    ) -> BuiltRequest:
        """Build an HTTP request envelope. Auth is applied separately by the caller."""
        endpoint_template = (
            service_config.get("endpoint")
            if service_config
            else self.request_config.get("endpoint", "/")
        )
        assert endpoint_template is not None, "endpoint_template must not be None"

        path_context = {"parameters": parameters}
        endpoint = self._render_template_string(endpoint_template, path_context)
        url = f"{self._base_url}{endpoint}"

        method_value = (
            service_config.get("method")
            if service_config
            else self.request_config.get("method", "POST")
        )
        method = (method_value or "POST").upper()

        webhook_endpoint = None
        if self.webhook_config.get("webhook_support"):
            webhook_endpoint = self._generate_webhook_url(
                provider_name=self._provider_name,
                organization_id=organization_id,
            )

        context: Dict[str, Any] = {
            "parameters": parameters,
            "system": {
                "webhook_endpoint": webhook_endpoint,
                "organization_id": str(organization_id),
            },
        }
        if credentials is not None:
            context["credentials"] = credentials

        headers = self._render_template_dict(
            self.request_config.get("headers", {}), context
        )

        param_mapping = (
            service_config.get("parameter_mapping", {}) if service_config else {}
        )
        query_param_names = set(param_mapping.get("query", []))
        body_param_names = set(param_mapping.get("body", []))

        request_transform = (
            service_config.get("request_transform", {}) if service_config else {}
        )
        body_transform = (
            request_transform.get("body")
            if isinstance(request_transform, dict)
            else None
        )
        query_transform = (
            request_transform.get("query_params")
            if isinstance(request_transform, dict)
            else None
        )

        body: Optional[Any] = None
        query_params: Dict[str, Any] = {}

        if method in ("GET", "DELETE", "HEAD"):
            if query_transform:
                rendered_q = self._render_template_dict(query_transform, context)
                rendered_q = self._strip_omit_sentinel(rendered_q)
                query_params = {k: v for k, v in rendered_q.items() if v is not None}
            else:
                query_params = self._get_query_params(parameters, endpoint_template)
        else:
            body_template = self.request_config.get("body_template", {})

            if body_transform:
                body = self._render_template_dict(body_transform, context)
                body = self._strip_omit_sentinel(body)
                if query_transform:
                    rendered_q = self._render_template_dict(query_transform, context)
                    rendered_q = self._strip_omit_sentinel(rendered_q)
                    query_params = {
                        k: v for k, v in rendered_q.items() if v is not None
                    }
            elif body_template:
                body = self._render_template_dict(body_template, context)
                body = self._strip_omit_sentinel(body)
            elif query_param_names or body_param_names:
                for k, v in parameters.items():
                    if v is None:
                        continue
                    if k in query_param_names:
                        query_params[k] = v
                if body_param_names:
                    body = {
                        k: v
                        for k, v in parameters.items()
                        if k in body_param_names and v is not None
                    }
                    if not body:
                        body = None
            elif parameters:
                # No mapping configured - send all parameters as body.
                body = parameters

        return BuiltRequest(
            url=url,
            method=method,
            headers=headers,
            body=body,
            query_params=query_params,
        )

    def _apply_auth(
        self, built: BuiltRequest, credentials: Dict[str, Any]
    ) -> BuiltRequest:
        """Merge auth into a copy of the request envelope; input is not mutated.

        Modes: bearer, custom (multi-field query), query_param, custom_header, header.
        """
        headers = dict(built.headers)
        query_params = dict(built.query_params or {})

        auth_type = self.auth_config.get("type", "bearer")

        if auth_type == "bearer":
            if "Authorization" not in headers:
                token_field = self.auth_config.get("config", {}).get(
                    "token_field", "api_key"
                )
                token = credentials.get(token_field) or credentials.get("api_key")
                if token:
                    headers["Authorization"] = f"Bearer {token}"

        elif auth_type == "custom":
            auth_fields = self.auth_config.get("config", {}).get("fields", [])
            if isinstance(auth_fields, dict):
                for cred_field, param_name in auth_fields.items():
                    if credentials.get(cred_field):
                        query_params[param_name] = credentials[cred_field]
            else:
                for cred_field in auth_fields:
                    if credentials.get(cred_field):
                        query_params[cred_field] = credentials[cred_field]

        elif auth_type == "query_param":
            param_name = self.auth_config.get("param_name", "key")
            value_source = self.auth_config.get("param_value_source", "api_key")
            if credentials.get(value_source):
                query_params[param_name] = credentials[value_source]

        elif auth_type == "custom_header":
            header_name = self.auth_config.get("header_name", "x-api-key")
            value_source = self.auth_config.get("header_value_source", "api_key")
            if credentials.get(value_source):
                headers[header_name] = credentials[value_source]

        elif auth_type == "header":
            header_name = self.auth_config.get("header", "x-api-key")
            if credentials.get("api_key"):
                headers[header_name] = credentials["api_key"]

        else:
            if "Authorization" not in headers and credentials.get("api_key"):
                headers["Authorization"] = f"Bearer {credentials['api_key']}"

        return replace(built, headers=headers, query_params=query_params)

    def _render_template_value(self, value: Any, context: Dict[str, Any]) -> Any:
        """Render a Jinja value, preserving native Python type for whole-expression strings.

        Mixed strings (e.g. "Bearer {{ expr }}") always render to str.
        """
        if not isinstance(value, str):
            return value
        match = _PURE_EXPR_RE.match(value)
        if match:
            expr = match.group(1)
            try:
                # undefined_to_none=False keeps StrictUndefined active - missing
                # variables raise instead of silently becoming None.
                result = self.jinja_env.compile_expression(
                    expr, undefined_to_none=False
                )(**context)
                if isinstance(result, jinja2.Undefined):
                    # Trigger StrictUndefined error rather than leak a sentinel.
                    str(result)
                return result
            except jinja2.UndefinedError:
                raise
            except Exception:
                return self.jinja_env.from_string(value).render(context)
        return self.jinja_env.from_string(value).render(context)

    def _render_template_dict(
        self, template_dict: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Recursively render Jinja templates; whole-expression strings keep native type."""
        result: Dict[str, Any] = {}

        for key, value in template_dict.items():
            if isinstance(value, str):
                result[key] = self._render_template_value(value, context)
            elif isinstance(value, dict):
                result[key] = self._render_template_dict(value, context)
            elif isinstance(value, list):
                result[key] = [
                    (
                        self._render_template_dict(item, context)
                        if isinstance(item, dict)
                        else self._render_template_value(item, context)
                    )
                    for item in value
                ]
            else:
                result[key] = value

        return result

    def _strip_omit_sentinel(self, value: Any) -> Any:
        """Recursively drop keys/items whose value equals OMIT_SENTINEL."""
        if isinstance(value, dict):
            return {
                k: self._strip_omit_sentinel(v)
                for k, v in value.items()
                if v != OMIT_SENTINEL
            }
        if isinstance(value, list):
            return [
                self._strip_omit_sentinel(item)
                for item in value
                if item != OMIT_SENTINEL
            ]
        return value

    def _render_template_string(
        self, template_str: str, context: Dict[str, Any]
    ) -> str:
        """Render a template string. Path-param syntax {name} is rewritten to Jinja before rendering."""
        import re

        def convert_path_param(match: re.Match[str]) -> str:
            param_name = match.group(1)
            return "{{ parameters." + param_name + " }}"

        # Match {word} but not {{word}}.
        converted = re.sub(
            r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})",
            convert_path_param,
            template_str,
        )

        template = self.jinja_env.from_string(converted)
        return template.render(context)

    def _get_query_params(
        self, parameters: Dict[str, Any], endpoint: str
    ) -> Dict[str, Any]:
        """All parameters not bound to path placeholders, with None values dropped."""
        import re

        path_params = set(re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", endpoint))

        return {
            k: v
            for k, v in parameters.items()
            if k not in path_params and v is not None
        }

    def _extract_response_data(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields via JSONPath; returns full response if no extract config is present."""
        extract_config = self.response_config.get("extract", {})

        if not extract_config:
            return response_data

        extracted = {}

        for field_name, jsonpath_expr in extract_config.items():
            try:
                parser = jsonpath_ng.parse(jsonpath_expr)
                matches = parser.find(response_data)

                if matches:
                    values = [m.value for m in matches]
                    extracted[field_name] = values[0] if len(values) == 1 else values
                else:
                    logger.warning(
                        f"JSONPath '{jsonpath_expr}' matched no values "
                        f"for field '{field_name}'"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to extract field '{field_name}' "
                    f"with JSONPath '{jsonpath_expr}': {e}"
                )

        return extracted if extracted else response_data

    def _extract_error_message(self, response: httpx.Response) -> str:
        try:
            error_data = response.json()
            error_path = self.error_config.get("error_message_path", "$.error")

            parser = jsonpath_ng.parse(error_path)
            matches = parser.find(error_data)

            if matches:
                return str(matches[0].value)

            return error_data.get("message") or error_data.get("error") or response.text

        except (ValueError, KeyError, TypeError):
            # JSON parse + jsonpath extraction errors expected here.
            return response.text or f"Status {response.status_code}"

    def _generate_webhook_url(
        self,
        provider_name: str,
        organization_id: UUID,
    ) -> str:
        base_url = "https://your-domain.com"
        return f"{base_url}/api/v1/webhooks/{provider_name.lower()}"

    async def validate_credentials(
        self,
        credentials: Dict[str, Any],
    ) -> CredentialValidationResult:
        """Validate credentials via the configured validation endpoint."""
        try:
            validation_config = self.config.get("validation_config", {})
            endpoint = validation_config.get("endpoint", "/")

            headers = self._render_template_dict(
                validation_config.get("headers", {}), {"credentials": credentials}
            )

            response = await self._request_with_retry(
                method="GET",
                url=f"{self._base_url}{endpoint}",
                headers=headers,
                timeout=settings.ADAPTER_CREDENTIAL_VALIDATION_TIMEOUT,
            )

            if response.status_code == 200:
                return CredentialValidationResult(valid=True)
            else:
                return CredentialValidationResult(
                    valid=False,
                    error=f"Credential validation failed: HTTP {response.status_code}",
                )

        except Exception as e:
            logger.exception("Credential validation failed")
            return CredentialValidationResult(
                valid=False, error=f"Validation error: {safe_error_message(e)}"
            )

    async def health_check(self) -> HealthCheckResult:
        """Ping the configured health endpoint (defaults to base URL)."""
        try:
            import time

            start = time.time()

            health_endpoint = self.config.get("health_check_endpoint", "/")
            url = f"{self._base_url}{health_endpoint}"

            response = await self._client.get(
                url, timeout=settings.ADAPTER_CREDENTIAL_VALIDATION_TIMEOUT
            )
            latency_ms = int((time.time() - start) * 1000)

            if response.status_code == 200:
                return HealthCheckResult(healthy=True, latency_ms=latency_ms)
            else:
                return HealthCheckResult(
                    healthy=False,
                    error=f"Health check returned HTTP {response.status_code}",
                    latency_ms=latency_ms,
                )

        except Exception as e:
            logger.exception("Health check failed")
            return HealthCheckResult(healthy=False, error=safe_error_message(e))

    def get_service_schema(self, service_id: str) -> Dict[str, Any]:
        # Schemas live in the DB; this is just a typed placeholder.
        return {
            "type": "object",
            "properties": {},
            "note": "Schema defined in database provider_services table",
        }
