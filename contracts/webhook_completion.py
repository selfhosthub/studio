# contracts/webhook_completion.py

"""Declarative webhook-completion capability (catalog -> API -> worker).

The inbound-callback ENVELOPE is a property of the provider's webhook API (one
shape for the whole provider), so it lives at the PROVIDER level. The parsing
tied to a specific endpoint (the create-response wrapper, the asset shape inside
the envelope) lives at the SERVICE level::

    # provider top-level - the inbound callback envelope (one per provider)
    "webhook_completion": {
        "id_callback_path":     "$.data.object.id",
        "status_callback_path": "$.data.object.status",
        "success_values":       ["COMPLETE"],
        "failure_values":       ["FAILED"],          # optional
        "auth": {"type": "bearer_header",
                 "credential_field": "webhook_callback_api_key"}
    }

    # per-service - parsing tied to THIS endpoint
    "services": {
      "text_to_image": {
        "completion_modes": ["get", "webhook"],
        "webhook_completion": {
            "id_response_path":     "$.sdGenerationJob.generationId",
            "result_callback_path": "$.data.object.images[*].url"
        }
      }
    }

The generic inbound handler reads these paths and imports no provider. This
module is the single source of truth for the required-path rule: the provider
installer audits a provider against it at install time (fail loud, never a
half-built listen mode), and ``scripts/check-webhook-completion-paths.py``
audits the catalog files at commit time.
"""

from typing import Any, Dict, List

# Membership value in a service's ``completion_modes`` array that opts the
# service into webhook listen mode. Absence => synchronous ``get`` polling.
WEBHOOK_MODE = "webhook"

# Required keys on the PROVIDER-level ``webhook_completion`` envelope when any
# service opts into webhook mode. ``failure_values`` is intentionally NOT here -
# it is optional (absence => any non-success terminal status is a failure).
# ``auth`` is required but validated structurally (see the audit) rather than by
# a truthiness check.
PROVIDER_REQUIRED_WEBHOOK_COMPLETION_PATHS = (
    "id_callback_path",
    "status_callback_path",
    "success_values",
    "auth",
)

# Required keys on the SERVICE-level ``webhook_completion`` block for a service
# in webhook mode (parsing tied to the specific endpoint).
SERVICE_REQUIRED_WEBHOOK_COMPLETION_PATHS = (
    "id_response_path",
    "result_callback_path",
)

# auth.type values the generic handler knows how to enforce.
#   bearer_header - validate ``Authorization: Bearer`` against ``credential_field``.
#   url_token     - the opaque callback_token in the URL is the only gate
#                   (e.g. json2video, which sends no auth header).
#   none          - no inbound auth.
KNOWN_AUTH_TYPES = ("bearer_header", "url_token", "none")


def audit_provider_webhook_completion(provider_data: Dict[str, Any]) -> List[str]:
    """Return a list of human-readable issues for a provider's webhook-completion
    config. Empty list => the provider is clean.

    Audited only when at least one service declares ``completion_modes``
    containing ``"webhook"``; a provider with no webhook services is ignored.
    When audited:

    * the PROVIDER-level ``webhook_completion`` envelope must declare every key
      in ``PROVIDER_REQUIRED_WEBHOOK_COMPLETION_PATHS`` with a truthy value, and
      its ``auth`` must declare a ``type`` (a ``bearer_header`` auth additionally
      requires ``credential_field``);
    * each webhook-mode SERVICE must declare every key in
      ``SERVICE_REQUIRED_WEBHOOK_COMPLETION_PATHS``.
    """
    issues: List[str] = []
    slug = provider_data.get("slug", "<unknown>")
    services = provider_data.get("services") or {}

    webhook_services = [
        (svc_slug, svc)
        for svc_slug, svc in services.items()
        if isinstance(svc, dict)
        and WEBHOOK_MODE in (svc.get("completion_modes") or [])
    ]
    if not webhook_services:
        return issues

    # Provider-level envelope: required once when any service opts in.
    envelope = provider_data.get("webhook_completion")
    if not isinstance(envelope, dict):
        issues.append(
            f"{slug}: a service declares completion_modes including "
            f"'{WEBHOOK_MODE}' but the provider-level webhook_completion "
            f"envelope is missing"
        )
    else:
        for key in PROVIDER_REQUIRED_WEBHOOK_COMPLETION_PATHS:
            if key == "auth":
                continue
            if not envelope.get(key):
                issues.append(
                    f"{slug}: provider webhook_completion is missing required '{key}'"
                )
        auth = envelope.get("auth")
        if not isinstance(auth, dict) or not auth.get("type"):
            issues.append(
                f"{slug}: provider webhook_completion.auth must declare a 'type'"
            )
        elif auth["type"] == "bearer_header" and not auth.get("credential_field"):
            issues.append(
                f"{slug}: provider webhook_completion.auth type 'bearer_header' "
                f"requires 'credential_field'"
            )

    # Service-level block: required per webhook-mode service.
    for svc_slug, svc in webhook_services:
        ref = f"{slug}.{svc_slug}"
        block = svc.get("webhook_completion")
        if not isinstance(block, dict):
            issues.append(
                f"{ref}: completion_modes includes '{WEBHOOK_MODE}' but the "
                f"service webhook_completion block is missing"
            )
            continue
        for key in SERVICE_REQUIRED_WEBHOOK_COMPLETION_PATHS:
            if not block.get(key):
                issues.append(
                    f"{ref}: service webhook_completion is missing required '{key}'"
                )

    return issues
