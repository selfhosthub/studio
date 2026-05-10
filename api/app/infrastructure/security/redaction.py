# api/app/infrastructure/security/redaction.py

"""Re-export of the authoritative redaction policy from contracts.

Do not add new symbols here - extend contracts/redaction.py instead.
Redaction belongs at egress boundaries (logs, HTTP responses); never at storage time.
"""

from contracts.redaction import (
    PII_KEYS,
    REDACTED_PLACEHOLDER,
    SENSITIVE_KEYS,
    is_pii_key,
    is_sensitive_key,
    redact_sensitive_data,
    redact_url,
)

__all__ = [
    "PII_KEYS",
    "REDACTED_PLACEHOLDER",
    "SENSITIVE_KEYS",
    "is_pii_key",
    "is_sensitive_key",
    "redact_sensitive_data",
    "redact_url",
]
