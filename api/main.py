# api/main.py

"""
Main application entry point.

This module initializes and runs the FastAPI application,
setting up the necessary routes, middleware, and database connections.
"""

import logging
import logging.config
import os
from contextlib import asynccontextmanager
from typing import Any, Dict

# Load environment variables BEFORE any app imports (they check env at import time)
from dotenv import load_dotenv

load_dotenv()  # Load .env (symlinked to /workspace/.env)
if os.getenv("SHS_ALLOW_ENV_LOCAL") == "1":
    load_dotenv("/workspace/.env.local", override=True)  # Override with secrets

from app import __version__  # noqa: E402 - must follow load_dotenv()
from app.config.settings import settings  # noqa: E402 - must follow load_dotenv()

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text


from app.infrastructure.logging.config import (
    RICH_AVAILABLE,
    get_base_log_config,
    get_log_config,
    get_json_log_config,
    setup_rich_logging,
    suppress_third_party_loggers,
)
from app.infrastructure.logging.filters import SuppressASGITracebackFilter
from app.infrastructure.logging.context_middleware import LoggingContextMiddleware
from app.infrastructure.persistence.database import db
from app.presentation.api.system_health import (
    get_maintenance_status,
)  # noqa: F401 - re-exported for middleware
from app.infrastructure.adapters.registry import AdapterRegistry
from app.infrastructure.adapters.provider_loader import initialize_providers
from app.infrastructure.orchestration.result_processor import ResultProcessor
from app.presentation.api import register_routers
from app.presentation.api.error_handlers import register_error_handlers
from app.presentation.webhooks import webhook_router
from app.presentation.websockets.handlers import router as websocket_router
from app.presentation.websockets.manager import manager as ws_manager
from app.infrastructure.messaging.pg_broadcaster import PgBroadcaster
from app.infrastructure.messaging.pg_notify import (
    notify_instance,
    notify_organization,
    notify_user,
)

# Configure logging with token redaction
ENABLE_ACCESS_LOGS = settings.ENABLE_ACCESS_LOGS
LOG_LEVEL = settings.LOG_LEVEL.upper()
LOG_FORMAT = settings.LOG_FORMAT.lower()
UVICORN_LOG_LEVEL = settings.UVICORN_LOG_LEVEL.upper()
UVICORN_ERROR_LOG_LEVEL = settings.UVICORN_ERROR_LOG_LEVEL.upper()

if LOG_FORMAT == "json":
    # JSON format - structured logs for ELK/Prometheus/Loki
    # Includes user_id and org_id for SOC 2 compliance
    logging.config.dictConfig(
        get_json_log_config(
            log_level=LOG_LEVEL,
            uvicorn_log_level=UVICORN_LOG_LEVEL,
            uvicorn_error_log_level=UVICORN_ERROR_LOG_LEVEL,
            enable_access_logs=ENABLE_ACCESS_LOGS,
        )
    )
elif LOG_FORMAT == "rich" and RICH_AVAILABLE:
    # Rich format - beautiful colored output
    setup_rich_logging(
        log_level=LOG_LEVEL,
        uvicorn_log_level=UVICORN_LOG_LEVEL,
        uvicorn_error_log_level=UVICORN_ERROR_LOG_LEVEL,
        enable_access_logs=ENABLE_ACCESS_LOGS,
    )
elif ENABLE_ACCESS_LOGS:
    # Full logging with access logs, token redaction, and health check filtering
    logging.config.dictConfig(
        get_log_config(
            log_level=LOG_LEVEL,
            uvicorn_log_level=UVICORN_LOG_LEVEL,
            uvicorn_error_log_level=UVICORN_ERROR_LOG_LEVEL,
        )
    )
else:
    # Basic logging without access logs (cleaner output for development)
    logging.config.dictConfig(
        get_base_log_config(
            log_level=LOG_LEVEL,
            uvicorn_log_level=UVICORN_LOG_LEVEL,
            uvicorn_error_log_level=UVICORN_ERROR_LOG_LEVEL,
            enable_access_logs=False,
        )
    )
    # NUCLEAR OPTION: Kill uvicorn.access completely
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.disabled = True
    access_logger.handlers.clear()
    access_logger.addHandler(logging.NullHandler())
    access_logger.setLevel(100)  # Higher than CRITICAL (50)
    access_logger.propagate = False


# Suppress noisy third-party loggers across all format paths
suppress_third_party_loggers()

# Suppress duplicate ASGI exception tracebacks from uvicorn.error
_uvicorn_error = logging.getLogger("uvicorn.error")
_uvicorn_error.addFilter(SuppressASGITracebackFilter())

logger = logging.getLogger(__name__)

# Global adapter registry instance
adapter_registry = AdapterRegistry()

# Initialize WebSocket event handlers and routes (deferred to avoid circular import)
from app.presentation.api.dependencies import init_ws_event_handlers

init_ws_event_handlers()


# Paths that are allowed during maintenance mode
MAINTENANCE_ALLOWED_PATHS = {
    "/health",
    "/api/v1/public/maintenance",
    "/api/v1/public/branding",
    "/api/v1/infrastructure/health/maintenance",  # Admin can check/toggle
    "/api/v1/infrastructure/health/maintenance/enable",
    "/api/v1/infrastructure/health/maintenance/disable",
    "/api/v1/infrastructure/health/maintenance/warn",
    "/docs",
    "/docs/",
    "/docs/dark",
    "/docs/slim",
    "/docs/models",
    "/openapi.json",
    "/openapi-minimal.json",
    "/static",
}


class MaintenanceMiddleware:
    """
    Pure ASGI middleware that blocks API requests during maintenance mode.

    Implemented as raw ASGI (not BaseHTTPMiddleware) so WebSocket upgrade
    requests pass through without being intercepted.

    Allows only:
    - Health check endpoints
    - Public maintenance status endpoint
    - Admin maintenance control endpoints
    - Static files and docs
    - WebSocket connections
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Only intercept HTTP requests - let WebSocket and lifespan pass through
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]

        # Allow specific paths during maintenance
        for allowed in MAINTENANCE_ALLOWED_PATHS:
            if path == allowed or path.startswith(allowed + "/"):
                await self.app(scope, receive, send)
                return

        # Allow static files and uploads
        if path.startswith("/static/") or path.startswith("/uploads/"):
            await self.app(scope, receive, send)
            return

        # Check maintenance mode (TTL-cached - cheap on cache hit)
        try:
            maint_status = await get_maintenance_status()
            if maint_status.maintenance_mode:
                response = JSONResponse(
                    status_code=503,
                    content={
                        "detail": maint_status.reason or "System is under maintenance",
                        "maintenance_mode": True,
                    },
                    headers={"Retry-After": "300"},
                )
                await response(scope, receive, send)
                return
        except Exception as e:
            # If maintenance check fails, don't block requests
            logger.warning(f"Failed to check maintenance mode in middleware: {e}")

        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the FastAPI application.

    This handles startup and shutdown events, initializing and
    closing database connections.

    Args:
        app: FastAPI application
    """
    try:
        # Kill uvicorn.access AGAIN at startup (in case uvicorn re-enabled it)
        if not ENABLE_ACCESS_LOGS:
            access_logger = logging.getLogger("uvicorn.access")
            access_logger.disabled = True
            access_logger.handlers.clear()
            access_logger.addHandler(logging.NullHandler())
            access_logger.setLevel(100)
            access_logger.propagate = False

        # Block startup if required secrets are missing (all environments)
        # Settings validates these at instantiation, but check explicitly for clear error
        if not settings.JWT_SECRET_KEY or not settings.WORKER_SHARED_SECRET:
            msg = "SHS_JWT_SECRET_KEY and/or SHS_WORKER_SHARED_SECRET not set - generate with: openssl rand -hex 32"
            logger.error(msg)
            raise SystemExit(msg)

        logger.info("Initializing application...")
        db.init()

        # Schema is owned by Alembic; bootstrap.py runs `alembic upgrade head`
        # before the API process starts (see api/scripts/bootstrap.py).
        # Detect a missing schema and emit a one-line breadcrumb so anyone
        # bypassing docker-entrypoint.sh (e.g. `make api-local`) gets a clear
        # hint instead of cryptic "relation does not exist" later.
        try:
            async with db.engine.begin() as conn:  # type: ignore[union-attr]
                row = (
                    await conn.execute(
                        text(
                            "SELECT 1 FROM information_schema.tables "
                            "WHERE table_schema='public' AND table_name='alembic_version'"
                        )
                    )
                ).first()
                if row is None:
                    logger.warning(
                        "No alembic_version table found. Run bootstrap.py / use "
                        "docker-entrypoint.sh - direct `alembic upgrade head` only "
                        "works on a fresh DB."
                    )
        except Exception as e:
            logger.debug(f"Schema-presence check skipped: {e}")

        # Seed system_settings maintenance row (idempotent - ON CONFLICT DO NOTHING)
        try:
            from app.infrastructure.maintenance.seed import seed_maintenance_row

            await seed_maintenance_row()
            logger.info("system_settings maintenance row ensured")
        except Exception as e:
            logger.error(f"Error seeding system_settings: {e}")

        # Load providers from database and register adapters
        logger.info("Loading provider adapters from database...")
        try:
            session = await db.get_session()
            try:
                provider_count = await initialize_providers(session, adapter_registry)
                logger.info(f"Successfully loaded {provider_count} provider adapters")
            finally:
                await session.close()
        except Exception as e:
            logger.error(f"Error loading provider adapters: {e}")
            logger.warning("Application will continue without provider adapters")

        # Start Postgres LISTEN/NOTIFY broadcaster (cross-instance WebSocket fan-out)
        pg_broadcaster = PgBroadcaster(ws_manager)
        await pg_broadcaster.start()
        app.state.pg_broadcaster = pg_broadcaster

        async def _broadcast_instance_update(
            organization_id: str, instance_id: str, ws_message: dict
        ) -> None:
            from uuid import UUID

            org_uuid = UUID(organization_id)
            inst_uuid = UUID(instance_id)
            await notify_organization(org_uuid, ws_message)
            await notify_instance(inst_uuid, ws_message)

        async def _broadcast_notification(user_id, message: dict) -> None:
            await notify_user(user_id, message)

        # Initialize result processor for direct step result processing
        assert db.session_factory is not None, "Database not initialized"
        result_processor = ResultProcessor(
            session_factory=db.session_factory,
            broadcast_instance_update_fn=_broadcast_instance_update,
            broadcast_notification_fn=_broadcast_notification,
        )
        app.state.result_processor = result_processor
        app.state.notifier = result_processor.notifier
        logger.info("Result processor initialized")

        # Start periodic cleanup (worker deregister + stale step sweep).
        # In-process scheduler - works for every deploy without external cron.
        # Fires `PERIODIC_CLEANUP_INTERVAL_SECONDS` after startup and every
        # interval thereafter. See docs/plans/workflow-scheduler.md for the
        # follow-up that will build the full scheduled-workflow feature on
        # top of this same primitive.
        from app.infrastructure.scheduling import (
            PeriodicScheduler,
            ScheduledTask,
        )
        from app.infrastructure.scheduling.cleanup_task import (
            build_cleanup_callback,
        )

        scheduler = PeriodicScheduler()
        scheduler.register(
            ScheduledTask(
                name="periodic_cleanup",
                interval_seconds=settings.PERIODIC_CLEANUP_INTERVAL_SECONDS,
                callback=build_cleanup_callback(
                    session_factory=db.session_factory,
                    notifier=result_processor.notifier,
                    process_result_fn=result_processor.process_result,
                ),
                # Hold the first run until after startup so boot logs stay
                # readable. Subsequent runs fire on the normal interval.
                initial_delay_seconds=float(settings.PERIODIC_CLEANUP_INTERVAL_SECONDS),
            )
        )
        await scheduler.start()
        app.state.scheduler = scheduler
        logger.info(
            f"Periodic cleanup scheduler started "
            f"(interval={settings.PERIODIC_CLEANUP_INTERVAL_SECONDS}s)"
        )

        # Sync docs from community source
        try:
            from app.config.docs_sync import sync_docs_on_boot

            docs_ok = await sync_docs_on_boot()
            if not docs_ok:
                logger.warning("Community source unreachable - docs not loaded")
                app.state.community_source_unreachable = True
            else:
                app.state.community_source_unreachable = False
        except Exception as e:
            logger.warning(f"Docs boot sync failed: {e}")
            app.state.community_source_unreachable = True

        logger.info("Application startup complete")
        yield
    finally:
        logger.info("Shutting down application...")
        pg_broadcaster = getattr(app.state, "pg_broadcaster", None)
        if pg_broadcaster is not None:
            await pg_broadcaster.stop()
        scheduler = getattr(app.state, "scheduler", None)
        if scheduler is not None:
            try:
                await scheduler.stop()
            except Exception as e:
                logger.error(f"Error stopping scheduler: {e}")
        try:
            await db.shutdown()
        except Exception as e:
            logger.error(f"Error shutting down database: {str(e)}")
        logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """
    Create and configure a FastAPI application.

    This function can be called by tests to create a fresh application instance.

    Returns:
        FastAPI application
    """
    app = FastAPI(
        title="Self-Host Studio API",
        description="API for media workflow orchestration and automation",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Parse CORS origins from settings
    cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add logging context middleware (extracts user_id, org_id, org_slug from JWT for logs)
    # Runs early so all log entries include request context
    app.add_middleware(LoggingContextMiddleware)

    # Add maintenance mode middleware (runs after CORS)
    app.add_middleware(MaintenanceMiddleware)

    register_error_handlers(app)

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """
        Global exception handler for all unhandled exceptions.

        Args:
            request: Request that caused the exception
            exc: Exception that was raised

        Returns:
            JSON response with error details
        """
        logger.error(
            f"Unhandled {type(exc).__name__} on {request.method} {request.url.path}: {exc}"
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred. Please try again later."},
        )

    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app/static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    else:
        logger.warning(f"Static directory not found: {static_dir}")

    # Mount workspace uploads directory for avatars and other user uploads
    workspace_path = settings.WORKSPACE_ROOT
    if not workspace_path:
        logger.error("SHS_WORKSPACE_ROOT environment variable is not set")
        raise RuntimeError("SHS_WORKSPACE_ROOT environment variable is not set")
    workspace_dir = workspace_path
    uploads_dir = os.path.join(workspace_dir, "orgs")
    if os.path.exists(uploads_dir):
        app.mount("/uploads/orgs", StaticFiles(directory=uploads_dir), name="uploads")
        logger.info(f"Mounted workspace uploads at /uploads/orgs -> {uploads_dir}")
    else:
        logger.warning(f"Workspace uploads directory does not exist: {uploads_dir}")

    register_routers(app)
    app.include_router(webhook_router)
    app.include_router(websocket_router)

    @app.get("/", include_in_schema=False)
    async def root():
        """Root endpoint redirects to API documentation."""
        return RedirectResponse(url="/docs")

    @app.get("/api-info")
    async def api_info() -> Dict[str, str]:
        """API information endpoint."""
        return {
            "name": "Self-Host Studio API",
            "version": __version__,
            "description": "Multi-tenant media workflow orchestration system with support for blueprints, workflows, and instances",
            "docs_url": "/docs",
            "openapi_url": "/openapi.json",
        }

    @app.get("/health")
    async def health_check():
        """
        Health check endpoint with minimal information disclosure.

        SECURITY: Only shows environment info for non-production environments
        to allow frontend E2E tests to verify they're not running against production.
        Production instances return minimal information to prevent reconnaissance.
        """
        # Get environment from settings
        environment = settings.ENV
        is_debug = settings.DEBUG

        # Base response - minimal info for production
        health_data: Dict[str, Any] = {
            "status": "ok",
        }

        # Only expose environment details in non-production modes
        # This allows E2E tests to verify environment while keeping production anonymous
        if environment != "production":
            health_data["environment"] = environment  # development, test, or e2e
            health_data["debug"] = is_debug

        # Check component health but don't expose details unless degraded
        database_ok = True

        try:
            if db.engine is None:
                database_ok = False
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            database_ok = False

        # Only expose component details if something is wrong
        if not database_ok:
            health_data["status"] = "degraded"
            # In non-production, show which component is degraded
            if environment != "production":
                health_data["components"] = {
                    "database": "error",
                }

        return health_data

    return app


app = create_app()


if __name__ == "__main__":
    port = settings.PORT
    debug = settings.DEBUG

    # Scope the reload watcher to the FastAPI source dir only. Without this,
    # uvicorn's stat-based watcher recursively polls everything under the cwd
    # (mounted submodules, catalog content, .venv) and burns ~40-50% CPU at
    # idle in the dev container. Resolves to /app/app in container and
    # <repo>/api/app when running natively via `make api-local`.
    source_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")

    # The logging config is already set up above via logging.config.dictConfig
    # Using log_config=None tells uvicorn to use our pre-configured logging
    # This ensures consistent log format across all loggers for log aggregation
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=debug,
        reload_dirs=[source_dir] if debug else None,
        reload_excludes=["*.pyc", "__pycache__", "tests/*", "*.log"],
        log_config=None,  # Use the logging config already set up above
        access_log=ENABLE_ACCESS_LOGS,  # Controlled by ENABLE_ACCESS_LOGS env var
    )
