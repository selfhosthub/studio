# api/app/domain/provider/credential_validity.py

"""One rule for whether a stored OAuth credential can still serve a request.

The preflight check and the worker's token fetch both ask this, so they ask
it here. A token that never expires (Slack issues no refresh token unless
token rotation is on) is valid; a refresh token only matters once an expiry
has passed.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

# Keeps the token alive for the length of the worker's request.
REFRESH_BUFFER = timedelta(minutes=5)


def access_token_is_live(credential: Any, buffer: timedelta = REFRESH_BUFFER) -> bool:
    """True when the stored access token exists and has not run out."""
    if not credential.credentials.get("access_token"):
        return False
    expires_at = credential.expires_at
    if expires_at is None:
        return True
    return expires_at > datetime.now(UTC) + buffer


def serve_stored_token(credential: Any, buffer: timedelta = REFRESH_BUFFER) -> bool:
    """True when the stored token should be used rather than refreshed.

    A dated token that is still ahead is served. Otherwise a refresh token
    wins, since only an undated token with nothing to refresh from has to be
    taken on faith.
    """
    expires_at = credential.expires_at
    if expires_at is not None:
        return expires_at > datetime.now(UTC) + buffer
    if credential.credentials.get("refresh_token"):
        return False
    return bool(credential.credentials.get("access_token"))


def needs_reauthorization(credential: Any, buffer: timedelta = REFRESH_BUFFER) -> bool:
    """True when the credential can neither serve a request nor be renewed."""
    if access_token_is_live(credential, buffer):
        return False
    return not credential.credentials.get("refresh_token")
