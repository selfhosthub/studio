# api/app/infrastructure/security/webhook_tokens.py

"""At-rest form of a row-level incoming webhook token: ciphertext plus a SHA-256 lookup hash."""

from typing import Optional, Tuple

from app.infrastructure.security.credential_encryption import get_credential_encryption
from app.infrastructure.security.worker_enrollment import hash_secret


def hash_webhook_token(token: str) -> str:
    """Lookup form of a webhook token, stored beside its ciphertext."""
    return hash_secret(token)


def seal_webhook_token(token: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Ciphertext and lookup hash of token, or (None, None) when there is no token."""
    if not token:
        return None, None
    return get_credential_encryption().encrypt(token), hash_webhook_token(token)


def open_webhook_token(stored: Optional[str]) -> Optional[str]:
    """Plaintext of a stored webhook token ciphertext, or None when there is none."""
    if not stored:
        return None
    return get_credential_encryption().decrypt(stored)
