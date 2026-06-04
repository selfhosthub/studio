# contracts/redaction.py

"""
Authoritative redaction policy shared by api/ and workers/.

Design principles
-----------------
1. **Storage is full and unmodified.** Replayable payloads (input_data,
   request_body, iteration_requests, output data) MUST be persisted intact.
   Do not redact before writing to the database or transmitting to another
   service that will persist the payload.

2. **Redaction happens at egress.** There are exactly three egress boundaries
   where redaction belongs:
   - Logs: a logging.Filter that scrubs record.args and record.__dict__ (extras)
     using the `SENSITIVE_KEYS` policy defined here.
   - HTTP responses: DTO serializers apply `redact_sensitive_data` to payloads
     that leave the API boundary to a user/operator.
   - Error telemetry (Sentry/Datadog): configured with the same SENSITIVE_KEYS.

3. **UUIDs are identifiers, not secrets.** This module does NOT truncate UUID
   strings. Partial UUID display is a log-aesthetic choice and must never
   touch stored data or HTTP payloads - otherwise replay breaks when the
   truncated value is fed back in as an identifier.

4. **True secrets should be encrypted at rest**, not merely redacted.
   Redaction is complementary, not a substitute. `CredentialEncryption`
   imports this module's `SENSITIVE_KEYS` - it is the sole authority for
   which dict-value fields get encrypted before DB storage.

Compliance notes
----------------
- Key list below is the authoritative source for "what counts as a secret"
  across api/ and workers/. Do not copy-paste into other modules.
  `CredentialEncryption` (infrastructure/security) and `AuditService`
  (application/services) both import from here - no parallel lists.
- Adding to the list is additive and safe; removing from the list is a
  security-posture change that requires review.
- Substring match semantics: `is_sensitive_key("leonardo_api_key")` is True
  because "api_key" is a substring. This is intentional - it covers
  provider-prefixed variants without requiring every provider's exact
  field name in this list.
- PII (email, phone, SSN, card) is NOT in this taxonomy. PII has a
  different policy (user-of-record may see their own; redact from logs)
  and needs its own list once regulatory pressure applies.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set
from urllib.parse import urlparse, urlunparse

# Single source of truth. Import this - do not redefine elsewhere.
#
# Every token is deliberately chosen for its substring-match behavior:
# "api_key" matches "leonardo_api_key"; "secret" matches "client_secret"
# and "webhook_secret"; "signing_key" matches itself; etc.
#
# Deliberately NOT included:
# - "value" - from legacy AuditService; would redact `output_value`,
#   `input_value`, `return_value` etc. Case-specific audit policy lives
#   in AuditService; it scopes by key-context, not by global substring.
#
# Included despite minor observability cost:
# - "key" - a credential dict may carry a bare "key" field (legacy
#   providers and SSH-style credentials). Side effect: keys containing
#   "key" as substring (`step_key`, `primary_key`) also match. Verified
#   via grep that these identifiers do not appear in logger extras or
#   DTO serializations as dict keys, so real-world observability impact
#   is minimal. Credential leak is not recoverable; observability is.
# - "token" - same rationale. Side effect: `max_tokens`, `token_count`,
#   `total_tokens` also match.
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "secret",
        "password",
        "hashed_password",
        "api_key",
        "apikey",
        "api-key",
        "key",
        "token",
        "auth_token",
        "authorization",
        "bearer",
        "credential_id",
        "credential",
        "access_key",
        "access_token",
        "refresh_token",
        "private_key",
        "secret_key",
        "client_secret",
        "auth",
        "aws_secret",
        "signing_key",
        "webhook_secret",
        "encryption_key",
    }
)

REDACTED_PLACEHOLDER = "[REDACTED]"

# ---------------------------------------------------------------------------
# PII taxonomy - separate from secrets, different policy.
#
# Secrets are never shown to anyone; PII may be visible to the owning user
# but must be scrubbed from application logs, cross-org responses, and error
# telemetry. This set covers the log-egress concern. Role-aware HTTP egress
# (user sees their own PII, operators see [REDACTED]) is future work.
#
# Substring-match semantics, same as SENSITIVE_KEYS: "email" matches
# "user_email", "from_email_address", etc. Deliberately broad - a false
# positive in logs is harmless; a PII leak is not.
# ---------------------------------------------------------------------------
PII_KEYS: frozenset[str] = frozenset(
    {
        "email",
        "phone",
        "phone_number",
        "full_name",
        "first_name",
        "last_name",
        "street_address",
        "mailing_address",
        "ssn",
        "social_security",
        "card_number",
        "credit_card",
        "date_of_birth",
    }
)


def is_pii_key(key: str) -> bool:
    """
    True if `key` contains any PII_KEYS token as a substring (case-insensitive).

    Same substring-match semantics as `is_sensitive_key`. Used by logging
    filters to scrub PII from log records.
    """
    lower = key.lower()
    return any(token in lower for token in PII_KEYS)


def is_sensitive_key(key: str) -> bool:
    """
    True if `key` contains any SENSITIVE_KEYS token as a substring (case-insensitive).

    Substring match is deliberate - e.g., `leonardo_api_key` and `X-API-KEY`
    must both match. Callers should never redact by value heuristics
    (value entropy, format); always by key.
    """
    lower = key.lower()
    return any(token in lower for token in SENSITIVE_KEYS)


def redact_sensitive_data(
    data: Any,
    *,
    custom_sensitive_keys: Optional[Set[str]] = None,
    include_pii: bool = True,
) -> Any:
    """
    Return a copy of `data` with values of sensitive keys replaced by
    REDACTED_PLACEHOLDER. Recurses into dicts and lists.

    Pass ``include_pii=False`` to expose PII to the owning user in HTTP responses.

    Use only at egress boundaries (logs, HTTP responses, error reporters).
    NEVER before persisting to the database.
    """
    if data is None:
        return None

    if custom_sensitive_keys:
        extra = {k.lower() for k in custom_sensitive_keys}

        def _is_sensitive(k: str) -> bool:
            lower_k = k.lower()
            return (
                is_sensitive_key(k)
                or (include_pii and is_pii_key(k))
                or any(t in lower_k for t in extra)
            )

    else:

        def _is_sensitive(k: str) -> bool:
            return is_sensitive_key(k) or (include_pii and is_pii_key(k))

    if isinstance(data, dict):
        out: Dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(key, str) and _is_sensitive(key):
                out[key] = REDACTED_PLACEHOLDER
            else:
                out[key] = redact_sensitive_data(
                    value,
                    custom_sensitive_keys=custom_sensitive_keys,
                    include_pii=include_pii,
                )
        return out

    if isinstance(data, list):
        return [
            redact_sensitive_data(
                item,
                custom_sensitive_keys=custom_sensitive_keys,
                include_pii=include_pii,
            )
            for item in data
        ]

    # Primitives pass through - no UUID truncation, no string munging.
    return data


def redact_url(url: Optional[str]) -> Optional[str]:
    """
    Strip query string and fragment from a URL for safe logging.

    S3 / CDN signed URLs carry credentials in their query string. The path
    and scheme stay visible for debugging; `?[REDACTED]` is a sentinel that
    "there was a query string and it was scrubbed".

    Returns None if input is None; returns the input unchanged if it is
    not a string (defensive - logger formatting shouldn't crash on bad input).

    Use at LOG TIME only. Stored URLs must keep their query string intact
    to remain fetchable.
    """
    if not url or not isinstance(url, str):
        return url
    parsed = urlparse(url)
    if parsed.query or parsed.fragment:
        clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        return f"{clean}?{REDACTED_PLACEHOLDER}"
    return url


__all__ = [
    "SENSITIVE_KEYS",
    "PII_KEYS",
    "REDACTED_PLACEHOLDER",
    "is_sensitive_key",
    "is_pii_key",
    "redact_sensitive_data",
    "redact_url",
]
