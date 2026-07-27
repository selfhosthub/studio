# workers/studio_workers/utils/security.py

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
from typing import Callable
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


def resolve_workspace_source(
    src: str, workspace_root: str
) -> "tuple[str | None, bool]":
    """Resolve a workspace source to ``(resolved_path, exists)``.

    Single shared implementation of the "is this a workspace file? validate
    and resolve it" wrapper that several engines previously open-coded around
    ``validate_virtual_path``. The path-derivation (esp. the security-sensitive
    URL parsing) lives here once instead of being copied per engine.

    Accepts two source shapes:

    - A bare virtual path: ``/orgs/{org}/instances/{inst}/file.ext`` (video
      engine sites - the API hands them the path directly).
    - A full API uploads URL: ``https://host/uploads/orgs/.../file.ext``
      (transfer worker - it receives the wire URL). Scheme and host are
      ignored on purpose: the API rewrites with its own public
      ``API_BASE_URL`` while workers run ``SHS_API_BASE_URL=http://api:8000``,
      so a host comparison would never match. The path AFTER the literal
      ``/uploads`` segment is taken as the workspace-relative path.

    Return shape is deliberately structured, NOT an overloaded ``Optional``:

    - ``(None, False)`` - ``src`` is **not a workspace source** (non-/orgs
      string, provider CDN URL, empty), OR it is hostile (path traversal /
      null byte - never surfaced as a usable path). The caller falls back to
      its own download/passthrough path.
    - ``(resolved_path, True)`` - workspace source, file present on disk.
    - ``(resolved_path, False)`` where ``resolved_path is not None`` -
      workspace source, validated path, but the file is **absent**.

    The "absent" case is reported, never decided here. Each caller keeps its
    own pre-consolidation behavior: some use the path regardless of ``exists``
    (and let the downstream consumer fail), some treat absent as "fall back".
    The helper must not pick - that was the silent-convergence risk.
    ``resolved_path is None`` is unambiguously "not a workspace source"; it is
    never used to signal "absent".
    """
    if not src:
        return None, False

    if src.startswith("/orgs/"):
        virtual_path = src
    elif src.startswith("http://") or src.startswith("https://"):
        marker = "/uploads/"
        idx = src.find(marker)
        if idx == -1:
            return None, False
        # Keep the leading slash of the workspace path; drop query/fragment.
        rest = src[idx + len(marker) - 1 :].split("?", 1)[0].split("#", 1)[0]
        if not rest or rest == "/":
            return None, False
        virtual_path = rest
    else:
        return None, False

    try:
        resolved = validate_virtual_path(virtual_path, workspace_root)
    except ValueError:
        # Hostile input is never surfaced as a usable path: report it as
        # "not a workspace source" so the caller's download path (with its
        # own SSRF defenses) handles it, exactly as before consolidation.
        return None, False

    return resolved, os.path.exists(resolved)


def resolve_media_source(
    virtual_path: str | None,
    url: str | None,
    workspace_root: str,
    download_fn: Callable[[str], str],
) -> str:
    """Resolve a media source to a local filesystem path.

    Uniform policy across all worker engines:

    1. If ``virtual_path`` is a workspace reference (``/orgs/...``), validate
       and stat it. File present -> return the resolved local path.
    2. Otherwise, if ``url`` is provided, call ``download_fn(url)`` and return
       the local path it produces. Each engine supplies its own ``download_fn``
       (httpx client, retries, cache dir, temp prefix) - the helper does not
       own download policy.
    3. If neither succeeds, raise ``FileNotFoundError`` with a classified
       message.

    Hostile ``virtual_path`` (path traversal or null byte) hard-raises
    ``ValueError`` even when a URL is present - hostile input is never
    silently rerouted, not even to a "safe" path. This diverges from the
    inner ``resolve_workspace_source`` primitive, which returns ``(None,
    False)`` so its callers can decide; this helper sits one layer up and
    makes the decision itself.

    Non-``/orgs/`` ``virtual_path`` values (including ``None``) are treated
    as "no workspace reference"; the URL fallback runs. The legacy
    ``create_video`` branch that treated bare strings as literal local paths
    is intentionally removed: workspace refs go through ``/orgs/...``,
    everything else is a URL.
    """
    if virtual_path and virtual_path.startswith("/orgs/"):
        resolved = validate_virtual_path(virtual_path, workspace_root)
        if os.path.exists(resolved):
            return resolved
    elif virtual_path and "\x00" in virtual_path:
        raise ValueError(f"Path contains null byte: '{virtual_path}'")

    if url:
        try:
            return download_fn(url)
        except Exception as e:
            logger.exception(
                "resolve_media_source: download_fn failed for url=%s", url
            )
            raise FileNotFoundError(
                f"{type(e).__name__} while fetching media. See worker logs."
            ) from e

    raise FileNotFoundError(
        "Media source unavailable: workspace file missing and no URL fallback. "
        "See worker logs."
    )


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
