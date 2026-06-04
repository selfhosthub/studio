# workers/shared/settings.py

"""
Shared worker settings - fields every worker needs regardless of engine.

Engine-specific fields live in each engine's own settings module so importing
this module never triggers validation of fields a given venv will never read.

Env-var prefix: SHS_ (e.g. SHS_API_BASE_URL, SHS_WORKER_TYPE).

Pydantic-settings precedence: process env > .env file > field defaults.
Docker Compose injects env before Python starts; native GPU workers (Mac,
RunPod) fall back to envs/.env.dev + envs/.env.local directly.
"""

from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.env_files import resolve_env_files

_ENVS_DIR = Path(__file__).resolve().parents[1] / "envs"
_ENV_FILES = resolve_env_files(_ENVS_DIR)


class SharedSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SHS_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ── Core (required - fail-fast at import) ────────────────────────────
    API_BASE_URL: str
    PUBLIC_BASE_URL: str
    WORKER_SHARED_SECRET: str
    WORKSPACE_ROOT: str

    # ── Core (optional) ──────────────────────────────────────────────────
    WORKER_TYPE: str = "general"
    WORKER_NAME: str | None = None  # auto-generated in worker_base if unset

    # ── Logging ──────────────────────────────────────────────────────────
    LOG_COLORS: bool = True
    LOG_FORMAT: str = "rich"
    LOG_LEVEL: str = "INFO"
    LOG_PREFIX: str = ""

    # ── Downloads ────────────────────────────────────────────────────────
    FILE_DOWNLOAD_MAX_MB: int = 100
    HTTP_CHUNK_SIZE: int = 65536
    MAX_DOWNLOAD_SIZE_MB: int = 500

    # ── Heartbeat ────────────────────────────────────────────────────────
    HEARTBEAT_INTERVAL_S: int = 60

    # ── HTTP Retry ───────────────────────────────────────────────────────
    HTTP_MAX_RETRIES: int = 3
    HTTP_RETRY_BACKOFF_FACTOR: float = 2.0
    HTTP_RETRY_BASE_DELAY: float = 1.0
    HTTP_RETRY_MAX_DELAY: float = 30.0
    PUBLISH_MAX_RETRIES: int = 3
    PUBLISH_RETRY_BASE_DELAY: float = 1.0
    PUBLISH_RETRY_MAX_DELAY: float = 10.0
    # When result publishing exhausts retries for a terminal status
    # (COMPLETED/FAILED), write the payload to {WORKSPACE_ROOT}/dead-letters/.
    # The API picks them up on its next cleanup tick and replays them via the
    # normal result processor. Closes the silent-orphan window for the
    # transient-API-5xx case. Requires worker workspace to be readable by API.
    DEAD_LETTER_ENABLED: bool = True
    TRANSFER_RETRY_BASE_DELAY: float = 2.0
    TRANSFER_RETRY_MAX_DELAY: float = 60.0

    # ── Image Processing (generic - used by general executor) ───────────
    THUMBNAIL_HEIGHT: int = 300
    THUMBNAIL_JPEG_QUALITY: int = 85
    THUMBNAIL_WIDTH: int = 300

    # ── Job Polling ──────────────────────────────────────────────────────
    # Exponential backoff progression: 5 → 10 → 20 → 40 → 60 (capped).
    # Cap must stay >= 60 to match the documented progression in
    # http_job_client._increase_backoff and the unit test that verifies it.
    JOB_POLL_BACKOFF_MAX_S: float = 60
    JOB_POLL_INTERVAL_S: float = 5

    # ── Startup ──────────────────────────────────────────────────────────
    API_STARTUP_MAX_RETRIES: int = 0
    API_STARTUP_RETRY_INTERVAL_S: int = 5

    # ── Timeouts (seconds) ───────────────────────────────────────────────
    FFPROBE_TIMEOUT_S: int = 30
    HEALTH_CHECK_TIMEOUT_S: float = 5
    HTTP_DOWNLOAD_TIMEOUT_S: int = 60
    HTTP_HANDLER_TIMEOUT_S: float = 60
    HTTP_INTERNAL_TIMEOUT_S: float = 30
    HTTP_VIDEO_DOWNLOAD_TIMEOUT_S: float = 120
    HTTP_WEBHOOK_TIMEOUT_S: int = 30
    JOB_CLAIM_TIMEOUT_S: int = 1
    SUBPROCESS_TIMEOUT_S: int = 10

    # ── Transfer ─────────────────────────────────────────────────────────
    TRANSFER_CHUNK_SIZE: int = 8 * 1024 * 1024
    TRANSFER_TIMEOUT_S: int = 3600

    # ── Worker Management ────────────────────────────────────────────────
    REGISTRATION_RETRY_INTERVAL: int = 30
    TOKEN_CACHE_MAX_SIZE: int = 100
    TOKEN_CACHE_TTL: int = 300
    WORKER_BUSY_TIMEOUT: int = 3600


settings = SharedSettings()  # type: ignore[call-arg]  # pydantic-settings loads from env

# Startup validation: PUBLIC_BASE_URL must not be a docker-internal address.
# External APIs (json2video, etc.) download files from this URL - it must be
# reachable from the public internet.
_INTERNAL_HOSTS = ("host.docker.internal", "api", "localhost", "127.0.0.1")
_pub_host = urlparse(settings.PUBLIC_BASE_URL).hostname or ""
if _pub_host in _INTERNAL_HOSTS:  # pragma: no branch - test env always uses localhost
    import logging as _logging

    _logging.getLogger(__name__).warning(
        "SHS_PUBLIC_BASE_URL=%s uses internal host '%s'. "
        "External APIs (json2video, etc.) will not be able to download files. "
        "Set this to a publicly-reachable URL or tunnel.",
        settings.PUBLIC_BASE_URL,
        _pub_host,
    )
