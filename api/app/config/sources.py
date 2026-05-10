# api/app/config/sources.py

"""Catalog/marketplace source resolution. Re-exports settings values plus URL/path helpers."""

from pathlib import Path

from app.config.settings import settings

COMMUNITY_SOURCE: str = settings.COMMUNITY_SOURCE
PLUS_SOURCE: str = settings.PLUS_SOURCE

PROVIDERS_DIRECTORY: str = settings.PROVIDERS_DIRECTORY
WORKFLOWS_DIRECTORY: str = settings.WORKFLOWS_DIRECTORY
PROMPTS_DIRECTORY: str = settings.PROMPTS_DIRECTORY
BLUEPRINTS_DIRECTORY: str = settings.BLUEPRINTS_DIRECTORY
COMFYUI_DIRECTORY: str = settings.COMFYUI_DIRECTORY


def is_remote(source: str) -> bool:
    return source.startswith("http")


# Startup guard - local sources must not reach production
if settings.ENV == "production":
    if not is_remote(COMMUNITY_SOURCE):
        raise RuntimeError(
            f"SHS_COMMUNITY_SOURCE must be a URL in production, got: {COMMUNITY_SOURCE!r}"
        )
    if not is_remote(PLUS_SOURCE):
        raise RuntimeError(
            f"SHS_PLUS_SOURCE must be a URL in production, got: {PLUS_SOURCE!r}"
        )


def build_url(source: str, *parts: str) -> str:
    """Join a remote source with path parts. Raises ValueError if source is local."""
    if not is_remote(source):
        raise ValueError(
            f"build_url() requires a remote source (http...), got: {source!r}"
        )
    return "/".join([source.rstrip("/"), *parts])


def source_for_tier(tier: str) -> str:
    """basic → COMMUNITY_SOURCE; advanced/plus → PLUS_SOURCE; unknown → COMMUNITY_SOURCE."""
    if tier in ("advanced", "plus"):
        return PLUS_SOURCE
    return COMMUNITY_SOURCE


def local_path(source: str, repo_root: str, *parts: str) -> Path:
    """Filesystem path from a local source. Raises ValueError if source is remote."""
    if is_remote(source):
        raise ValueError(
            f"local_path() requires a local source (directory name), got: {source!r}"
        )
    if parts:
        return Path(repo_root) / source / Path(*parts)
    return Path(repo_root) / source
