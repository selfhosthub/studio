# workers/studio_workers/utils/cf_access.py

"""Cloudflare Access service-token headers for outbound API requests."""

from typing import Dict

from studio_workers.settings import settings


def cf_access_headers() -> Dict[str, str]:
    """Return CF Access service-token headers; {} when either setting is unset."""
    if not settings.CF_ACCESS_CLIENT_ID or not settings.CF_ACCESS_CLIENT_SECRET:
        return {}
    return {
        "CF-Access-Client-Id": settings.CF_ACCESS_CLIENT_ID,
        "CF-Access-Client-Secret": settings.CF_ACCESS_CLIENT_SECRET,
    }
