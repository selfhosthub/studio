# api/app/infrastructure/security/asset_signing.py

"""HMAC-signed, time-limited URLs for unauthenticated provider asset fetches."""

import hashlib
import hmac
import time

from app.config.settings import settings


def _message(org_id: str, rel_path: str, exp: int) -> bytes:
    return f"{org_id}:{rel_path}:{exp}".encode()


def sign_asset(org_id: str, rel_path: str, exp: int) -> str:
    """HMAC-SHA256 over (org_id, rel_path, exp) keyed by the JWT secret."""
    return hmac.new(
        settings.JWT_SECRET_KEY.encode(),
        _message(org_id, rel_path, exp),
        hashlib.sha256,
    ).hexdigest()


def build_signed_asset_path(org_id: str, rel_path: str) -> str:
    """Return the signed, server-relative asset URL: /api/v1/public/assets/{org}/{rel}?exp&sig."""
    exp = int(time.time()) + settings.SIGNED_URL_TTL_SECONDS
    sig = sign_asset(org_id, rel_path, exp)
    return f"/api/v1/public/assets/{org_id}/{rel_path}?exp={exp}&sig={sig}"


def verify_asset(org_id: str, rel_path: str, exp: int, sig: str) -> bool:
    """True if the signature is valid and not expired."""
    if exp < int(time.time()):
        return False
    return hmac.compare_digest(sign_asset(org_id, rel_path, exp), sig)
