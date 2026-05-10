# workers/shared/utils/security.py

"""
Security utilities for input validation.

Provides path traversal protection and SSRF prevention for worker code
that handles user-supplied URLs and virtual file paths.
"""

import ipaddress
import logging
import os
import re
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Valid hex color: optional #, then 6 hex digits
_HEX_COLOR_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")

# Named colors accepted by FFmpeg
_NAMED_COLORS = frozenset(
    {
        "black",
        "white",
        "red",
        "green",
        "blue",
        "yellow",
        "cyan",
        "magenta",
        "gray",
        "grey",
        "orange",
        "purple",
        "pink",
        "brown",
        "transparent",
    }
)


def validate_virtual_path(path: str, workspace_root: str) -> str:
    """Resolve a virtual path against the workspace root; raises ValueError on path traversal.

    path: e.g. /orgs/abc/instances/def/file.png
    workspace_root: the allowed root directory (e.g. /workspace)
    """
    if "\x00" in path:
        raise ValueError(f"Path contains null byte: '{path}'")

    # Join workspace root with the virtual path (strip leading /)
    joined = os.path.join(workspace_root, path.lstrip("/"))
    resolved = os.path.realpath(joined)
    real_root = os.path.realpath(workspace_root)

    if not resolved.startswith(real_root + os.sep) and resolved != real_root:
        raise ValueError(f"Path traversal blocked: '{path}' resolves outside workspace")

    return resolved


def validate_url_scheme(url: str) -> None:
    """Validate that a URL is safe to fetch (blocks SSRF targets and non-http/s schemes).

    Loopback is allowed - workers reach the host API via localhost in Docker.
    """
    parsed = urlparse(url)

    # Only allow http and https
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Disallowed URL scheme: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"URL has no hostname: {url}")

    # Check if hostname is an IP address in a blocked range
    # Allow loopback (127.x) - workers use localhost to reach the host API.
    # Block link-local (169.254.x - cloud metadata) and private networks.
    try:
        addr = ipaddress.ip_address(hostname)
        _check_blocked_ip(addr, hostname)
    except ValueError as e:
        # If it's our own raised ValueError, re-raise
        if "URL targets" in str(e) or "Disallowed" in str(e):
            raise
        # Otherwise hostname is not an IP literal - resolve DNS to guard against
        # DNS rebinding (domain that resolves to private/link-local IPs).
        try:
            infos = socket.getaddrinfo(
                hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
            )
            for family, _, _, _, sockaddr in infos:
                resolved_ip = ipaddress.ip_address(sockaddr[0])
                _check_blocked_ip(resolved_ip, hostname)
        except socket.gaierror:
            # DNS resolution failed - let the HTTP client handle it
            pass


def _check_blocked_ip(
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address, hostname: str
) -> None:
    """Raise ValueError if addr is in a blocked IP range."""
    if addr.is_link_local:
        raise ValueError(
            f"URL targets link-local address (cloud metadata risk): {hostname}"
        )
    if addr.is_private and not addr.is_loopback:
        raise ValueError(f"URL targets private network address: {hostname}")


def validate_padding_color(color: str | None) -> str:
    """Validate a padding color for FFmpeg; returns 'black' as safe default for invalid input."""
    if not color or not isinstance(color, str):
        return "black"

    stripped = color.strip()

    if _HEX_COLOR_RE.match(stripped):
        return stripped

    if stripped.lower() in _NAMED_COLORS:
        return stripped.lower()

    logger.warning(f"Invalid padding_color '{stripped}', defaulting to 'black'")
    return "black"
