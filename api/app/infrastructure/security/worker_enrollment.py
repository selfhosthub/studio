# api/app/infrastructure/security/worker_enrollment.py

"""Minting and verification for worker join tokens and enrollment credentials.

Both are high-entropy machine secrets stored as a SHA-256 hash. The hash is the
lookup key, so a presented secret resolves in one indexed read.
"""

import hashlib
import secrets

JOIN_TOKEN_PREFIX = "shsjoin_"
CREDENTIAL_PREFIX = "shswrk_"

_ENTROPY_BYTES = 32


def _mint(prefix: str) -> str:
    return f"{prefix}{secrets.token_urlsafe(_ENTROPY_BYTES)}"


def mint_join_token() -> str:
    """A short-lived, single-use token an admin hands to a worker operator."""
    return _mint(JOIN_TOKEN_PREFIX)


def mint_credential() -> str:
    """The long-lived, revocable secret a worker keeps after enrolling."""
    return _mint(CREDENTIAL_PREFIX)


def hash_secret(secret: str) -> str:
    """SHA-256 hex of the presented secret; the stored lookup key."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def looks_like_credential(value: str) -> bool:
    """Whether a presented value is an enrollment credential rather than the shared secret."""
    return value.startswith(CREDENTIAL_PREFIX)


def looks_like_join_token(value: str) -> bool:
    return value.startswith(JOIN_TOKEN_PREFIX)
