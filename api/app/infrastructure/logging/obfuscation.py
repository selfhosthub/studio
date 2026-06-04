# api/app/infrastructure/logging/obfuscation.py

"""Log obfuscation helpers - truncate UUIDs and mask emails."""

from uuid import UUID


def mask_id(value: object) -> str:
    """Truncate a UUID to its first 8 hex chars; return input unchanged if not a UUID.

    >>> mask_id("87fc0b50-a0b0-5bf2-b3fd-20efbf5a4b68")
    '87fc0b50...'
    """
    text = str(value).strip()
    hex_only = text.replace("-", "")
    if len(hex_only) == 32:
        try:
            UUID(text)
            return f"{hex_only[:8]}..."
        except ValueError:
            pass
    return text


def mask_email(value: object) -> str:
    """Show first 3 chars of the local part plus the full domain.

    >>> mask_email("jane.admin@acmecorp.com")
    'jan...@acmecorp.com'
    """
    text = str(value).strip()
    if "@" not in text:
        return text
    local, domain = text.rsplit("@", 1)
    visible = min(3, len(local))
    return f"{local[:visible]}...@{domain}"
