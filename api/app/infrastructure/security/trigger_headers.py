# api/app/infrastructure/security/trigger_headers.py

"""Copy of an inbound trigger request's headers that is safe to keep on an instance."""

from typing import Any, Dict, Optional

from app.infrastructure.security.redaction import redact_sensitive_data

TRIGGER_SECRET_HEADER_TOKENS = frozenset({"signature", "hmac", "cookie"})


def redact_trigger_headers(
    headers: Dict[str, Any],
    auth_header_name: Optional[str],
    webhook_config: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Headers with secret-class, signature, cookie and configured auth header values redacted."""
    signature_header = ((webhook_config or {}).get("auth") or {}).get("signature_header")
    custom = set(TRIGGER_SECRET_HEADER_TOKENS)
    custom.update(str(n).lower() for n in (auth_header_name, signature_header) if n)
    return redact_sensitive_data(dict(headers), custom_sensitive_keys=custom)
