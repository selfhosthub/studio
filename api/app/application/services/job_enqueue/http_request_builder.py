# api/app/application/services/job_enqueue/http_request_builder.py

"""Enqueue-time HTTP wire-envelope builder.

Produces the http_request dict attached to job payloads so workers can fire
the pre-built request instead of re-running the adapter transform.
Credentials are excluded - auth merges at fire time from claim-fetched credentials.
"""

import logging
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def build_adapter_for_endpoint(endpoint: Any) -> Optional[Any]:
    """Construct a transient HTTP adapter for enqueue-time request building.

    Returns None for endpoints that don't route through the generic HTTP
    adapter (local-worker / direct-URL / provider-not-found paths).

    Iteration fan-out should call this once and pass the adapter into each
    per-iteration call - adapter construction includes an SSL context and
    connection pool (~3ms) that would dominate enqueue-transaction duration
    if built per-iteration.
    """
    if not endpoint.provider_adapter_config:
        return None
    if endpoint.local_worker and endpoint.local_worker.get("enabled"):
        return None
    # Core flow services (core.poll_service, core.approval, etc.) carry a
    # provider_adapter_config for credential lookup but have no upstream URL
    # to fire - they execute worker-side. Without a base_url there's no
    # wire envelope to pre-build, and GenericHTTPAdapter would crash on
    # `None.rstrip("/")` in BaseProviderAdapter.__init__.
    if not endpoint.provider_adapter_config.get("base_url"):
        return None

    from app.infrastructure.adapters.generic_http_adapter import GenericHTTPAdapter

    return GenericHTTPAdapter(endpoint.provider_adapter_config)


def try_build_http_request(
    endpoint: Any,
    resolved_step_config: Dict[str, Any],
    organization_id: uuid.UUID,
    step_id: str,
    adapter: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """Produce the wire envelope for HTTP-provider jobs at enqueue time.

    Returns a plain-dict envelope (url / method / headers / body /
    query_params) for jobs that route through the generic HTTP adapter.
    Returns None for local-worker / direct-URL / provider-not-found paths.

    Pass a pre-built adapter to amortize the cost across a fan-out batch.
    When omitted, an adapter is constructed here for the single-step path.

    Credentials are intentionally excluded: auth merges at fire time using
    claim-fetched credentials, so credential template vars would render empty.
    Any config relying on credentials inside the body is a security smell.

    Failure is logged and swallowed - envelope building must never block enqueueing.
    """
    try:
        if adapter is None:
            adapter = build_adapter_for_endpoint(endpoint)
        if adapter is None:
            return None

        # Only include keys when the underlying value is non-None.
        # GenericHTTPAdapter.build_request uses `.get(key, {})` on this
        # dict, so an explicit `None` value would leak through and break
        # subsequent `.get` calls on the returned `None`.
        service_config: Dict[str, Any] = {
            "endpoint": endpoint.service_endpoint_path,
            "method": endpoint.http_method,
        }
        if endpoint.parameter_mapping is not None:
            service_config["parameter_mapping"] = endpoint.parameter_mapping
        if endpoint.request_transform is not None:
            service_config["request_transform"] = endpoint.request_transform

        job_cfg = resolved_step_config.get("job") or {}
        parameters = job_cfg.get("parameters") or {}

        built = adapter.build_request(
            service_config=service_config,
            parameters=parameters,
            organization_id=organization_id,
            credentials=None,
        )
        return {
            "url": built.url,
            "method": built.method,
            "headers": built.headers,
            "body": built.body,
            "query_params": built.query_params,
        }
    except Exception as e:
        logger.warning(f"Step {step_id}: http_request dual-write skipped: {e}")
        return None
