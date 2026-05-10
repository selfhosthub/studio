# api/app/config/settings.py

"""Single source of truth for env vars. SHS_ prefix. No os.getenv in app code (scripts excepted)."""

from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Loaded from SHS_-prefixed environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="SHS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ── Core ─────────────────────────────────────────────────────────────

    DEBUG: bool = Field(default=False)
    ENV: str = Field(default="development")
    PORT: int = Field(default=8000)
    RUNNING_IN_DOCKER: bool = Field(default=False)

    # ── Database ─────────────────────────────────────────────────────────

    DATABASE_URL: str = Field(description="Postgres connection URL. Required.")
    DB_POOL_SIZE: int = Field(default=20)
    DB_MAX_OVERFLOW: int = Field(default=30)
    DB_POOL_TIMEOUT: int = Field(default=10)
    DB_POOL_RECYCLE: int = Field(default=1800)
    TEST_DATABASE_URL: Optional[str] = Field(default=None)

    # ── Security ─────────────────────────────────────────────────────────

    CREDENTIAL_ENCRYPTION_KEY: Optional[str] = Field(default=None)
    JWT_SECRET_KEY: str = Field(description="JWT signing secret. Required.")
    WORKER_SHARED_SECRET: str = Field(
        description="Shared secret for worker authentication. Required."
    )

    # ── Auth Tokens ──────────────────────────────────────────────────────

    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7)
    WEBHOOK_TOKEN_EXPIRE_HOURS: int = Field(default=24)
    WORKER_TOKEN_EXPIRE_MINUTES: int = Field(default=5)

    # ── Server ───────────────────────────────────────────────────────────

    API_BASE_URL: str = Field(default="")
    CORS_ORIGINS: str = Field(
        description="Comma-separated list of allowed CORS origins. Required."
    )
    DOCS_PATH: str = Field(default="/app/docs")
    FRONTEND_URL: str = Field(default="")
    STORAGE_BACKEND: str = Field(default="local")
    WORKSPACE_ROOT: Optional[str] = Field(default=None)

    # ── Logging ──────────────────────────────────────────────────────────

    API_SERVICE_NAME: str = Field(default="api")
    ENABLE_ACCESS_LOGS: bool = Field(default=False)
    LOG_COLORS: bool = Field(default=True)
    LOG_FORMAT: str = Field(default="rich")
    LOG_LEVEL: str = Field(default="INFO")
    SUPPRESS_ACCESS_LOG_SUCCESS: bool = Field(default=True)
    SUPPRESS_WEBSOCKET_LOGS: bool = Field(default=True)
    SUPPRESS_WORKER_POLLING_LOGS: bool = Field(default=True)
    UVICORN_ERROR_LOG_LEVEL: str = Field(default="ERROR")
    UVICORN_LOG_LEVEL: str = Field(default="INFO")

    # ── HTTP Timeouts (seconds) ──────────────────────────────────────────

    ADAPTER_CLIENT_TIMEOUT: float = Field(default=60.0)
    ADAPTER_CREDENTIAL_VALIDATION_TIMEOUT: float = Field(default=10.0)
    ADAPTER_POLL_REQUEST_TIMEOUT: float = Field(default=30.0)
    MARKETPLACE_CATALOG_TIMEOUT: float = Field(default=10.0)
    MARKETPLACE_DOWNLOAD_TIMEOUT: float = Field(default=30.0)
    PACKAGE_DOWNLOAD_TIMEOUT: float = Field(default=60.0)
    WEBHOOK_TIMEOUT: float = Field(default=30.0)

    # ── Adapter Polling ──────────────────────────────────────────────────

    ADAPTER_DEFAULT_MAX_ATTEMPTS: int = Field(default=60)
    ADAPTER_DEFAULT_POLL_INTERVAL: float = Field(default=10.0)
    ADAPTER_DEFAULT_TOTAL_TIMEOUT: float = Field(default=600.0)
    BASE_ADAPTER_INITIAL_DELAY: float = Field(default=2.0)
    BASE_ADAPTER_MAX_POLL_ATTEMPTS: int = Field(default=15)
    BASE_ADAPTER_POLL_INTERVAL: float = Field(default=2.0)

    # ── Worker Management ────────────────────────────────────────────────

    WARN_NO_WORKERS: bool = Field(default=True)
    WORKER_CLEANUP_RETENTION_MINUTES: int = Field(default=30)
    WORKER_HEARTBEAT_TIMEOUT_MINUTES: int = Field(default=3)

    # Stale step sweep - fails steps stuck in QUEUED/RUNNING/PENDING with no
    # activity beyond this threshold. Protects against workers crashing mid-job,
    # result publish failures, and transient API 5xx that leave steps orphaned.
    # Dev: 10 min. Prod: 15 min. Set longer if you have legitimately long-running
    # workers (video renders, model training).
    STALE_STEP_TIMEOUT_MINUTES: int = Field(default=15)

    # Periodic cleanup interval - how often the in-process scheduler fires the
    # cleanup cycle (worker deregister + stale step sweep + dead-letter replay).
    # Lower → faster detection, more DB chatter. Higher → cheaper, longer
    # operator wait before stuck instances surface.
    PERIODIC_CLEANUP_INTERVAL_SECONDS: int = Field(default=60)

    # ── Pagination ───────────────────────────────────────────────────────

    API_PAGE_LIMIT_DEFAULT: int = Field(default=100)
    API_PAGE_LIMIT_MEDIUM: int = Field(default=50)
    API_PAGE_LIMIT_RESOURCE: int = Field(default=20)
    API_PAGE_LIMIT_SMALL: int = Field(default=25)
    API_PAGE_MAX: int = Field(default=100)

    # ── Billing & Org Defaults ───────────────────────────────────────────

    DEFAULT_TRIAL_DAYS: int = Field(default=14)
    PENDING_ORG_MAX_EXECUTIONS: int = Field(default=0)
    PENDING_ORG_MAX_STORAGE_MB: int = Field(default=50)
    PENDING_ORG_MAX_USERS: int = Field(default=1)

    # ── Grace Periods & Buffers ──────────────────────────────────────────

    GRACE_HOURS_BLUEPRINTS: int = Field(default=72)
    GRACE_HOURS_STORAGE: int = Field(default=168)
    GRACE_HOURS_WORKFLOWS: int = Field(default=72)
    LICENSE_CACHE_TTL: int = Field(default=86400)
    LIMIT_BUFFER_BLUEPRINTS: int = Field(default=5)
    LIMIT_BUFFER_STORAGE_MB: int = Field(default=1024)
    LIMIT_BUFFER_USERS: int = Field(default=3)
    LIMIT_BUFFER_WORKFLOWS: int = Field(default=10)

    # ── Thumbnails ───────────────────────────────────────────────────────

    THUMBNAIL_MAX_SIZE: int = Field(default=256)
    THUMBNAIL_QUALITY: int = Field(default=85)

    # ── OAuth ────────────────────────────────────────────────────────────

    OAUTH_STATE_EXPIRY: int = Field(default=600)

    # ── Jobs ─────────────────────────────────────────────────────────────

    JOB_RETRY_LIMIT: int = Field(default=3)
    RESULT_CONSUMER_RETRY_PAUSE: int = Field(default=1)

    # ── Queue Defaults ───────────────────────────────────────────────────

    DEFAULT_FETCH_LIMIT: int = Field(default=1000)
    QUEUE_DEFAULT_MAX_CONCURRENCY: int = Field(default=10)
    QUEUE_DEFAULT_MAX_PENDING: int = Field(default=1000)
    QUEUE_DEFAULT_TIMEOUT: int = Field(default=3600)

    # ── Retry / Step Defaults ────────────────────────────────────────────

    DEFAULT_MAX_RETRIES: int = Field(default=3)
    DEFAULT_RETRY_DELAY_SECONDS: int = Field(default=60)
    STEP_DEFAULT_RETRY_COUNT: int = Field(default=0)
    STEP_DEFAULT_RETRY_DELAY: int = Field(default=60)

    # ── System Health ────────────────────────────────────────────────────

    LOG_TAIL_DEFAULT: int = Field(default=100)
    LOG_TAIL_MAX: int = Field(default=1000)
    SYSTEM_HEALTH_DEFAULT_PAGE: int = Field(default=10)
    SYSTEM_HEALTH_MAX_PAGE: int = Field(default=100)

    # ── Catalog & Marketplace ────────────────────────────────────────────

    BLUEPRINTS_DIRECTORY: str = Field(default="blueprints")
    CATALOG_CACHE_HOURS: int = Field(default=24)
    COMFYUI_DIRECTORY: str = Field(default="comfyui")
    COMMUNITY_SOURCE: str = Field(
        description="Community catalog source (dir name or URL). Required."
    )
    ENTITLEMENT_TOKEN: str = Field(default="")
    PLUS_SOURCE: str = Field(
        description="Plus catalog source (dir name or URL). Required."
    )
    PROMPTS_DIRECTORY: str = Field(default="prompts")
    PROVIDERS_DIRECTORY: str = Field(default="providers")
    WORKFLOWS_DIRECTORY: str = Field(default="workflows")

    # ── Admin Bootstrap ──────────────────────────────────────────────────

    ADMIN_EMAIL: str = Field(default="admin@example.com")
    ADMIN_PASSWORD: Optional[str] = Field(default=None)

    # ── Limits ───────────────────────────────────────────────────────────

    AVATAR_MAX_FILE_SIZE: int = Field(default=5 * 1024 * 1024)
    LIMIT_CRITICAL_THRESHOLD: float = Field(default=0.95)
    LIMIT_WARNING_THRESHOLD: float = Field(default=0.80)
    WEBHOOK_SECRET_LENGTH: int = Field(default=32)
    WEBHOOK_TOKEN_LENGTH: int = Field(default=24)

    # ── WebSocket ────────────────────────────────────────────────────────

    WS_IDLE_TIMEOUT_SECONDS: int = Field(default=300)
    WS_MAX_CONNECTIONS_PER_IP: int = Field(default=10)
    WS_MAX_TOTAL_CONNECTIONS: int = Field(default=1000)
    WS_MESSAGE_RATE_LIMIT: int = Field(default=30)
    WS_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60)
    # Per-connection broadcast send timeout. Half-open sockets (laptop sleep,
    # dropped TCP without FIN) accept bytes into the kernel send buffer until
    # it fills, then send_text parks waiting for ACKs that never arrive.
    # Without a bound, any caller awaiting the broadcast hangs indefinitely.
    WS_SEND_TIMEOUT_SECONDS: float = Field(default=2.0)

    # ── Maintenance ──────────────────────────────────────────────────────

    MAINTENANCE_MODE: bool = Field(default=False)

    # ── Validators ───────────────────────────────────────────────────────

    @field_validator("DATABASE_URL", "TEST_DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: Optional[str]) -> Optional[str]:
        """Force asyncpg driver on Postgres URLs."""
        if v and "postgresql://" in v and "+asyncpg" not in v:
            return v.replace("postgresql://", "postgresql+asyncpg://")
        return v


settings = Settings()  # type: ignore[call-arg]  # pydantic-settings loads from env
