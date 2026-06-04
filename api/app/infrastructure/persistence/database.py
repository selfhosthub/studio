# api/app/infrastructure/persistence/database.py

"""DB connection and session management with optional RLS for org isolation."""

import logging
from typing import Any, AsyncGenerator, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def __getattr__(name: str):
    """Lazy module-level `DATABASE_URL` — resolved on first read so importing
    this module (e.g. from Alembic's env.py via the package __init__)
    doesn't trigger full Settings validation.
    """
    if name == "DATABASE_URL":
        return get_settings().DATABASE_URL
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class Database:
    """Database connection manager."""

    def __init__(
        self,
        db_url: Optional[str] = None,
        echo: bool = False,
        pool_size: Optional[int] = None,
        max_overflow: Optional[int] = None,
        pool_timeout: Optional[int] = None,
        pool_recycle: Optional[int] = None,
    ):
        # Defaults resolve from Settings only at init() time so this class
        # can be instantiated at module load without env validation.
        self._db_url_override = db_url
        self._pool_size_override = pool_size
        self._max_overflow_override = max_overflow
        self._pool_timeout_override = pool_timeout
        self._pool_recycle_override = pool_recycle
        self.db_url: Optional[str] = None
        self.pool_size = 0
        self.max_overflow = 0
        self.pool_timeout = 0
        self.pool_recycle = 0
        self.echo = echo
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    def init(self) -> None:
        # Resolve any unset values from Settings now (lazy — first use only).
        s = get_settings()
        self.db_url = self._db_url_override or s.DATABASE_URL
        self.pool_size = (
            self._pool_size_override
            if self._pool_size_override is not None
            else s.DB_POOL_SIZE
        )
        self.max_overflow = (
            self._max_overflow_override
            if self._max_overflow_override is not None
            else s.DB_MAX_OVERFLOW
        )
        self.pool_timeout = (
            self._pool_timeout_override
            if self._pool_timeout_override is not None
            else s.DB_POOL_TIMEOUT
        )
        self.pool_recycle = (
            self._pool_recycle_override
            if self._pool_recycle_override is not None
            else s.DB_POOL_RECYCLE
        )

        logger.info(f"Initializing database connection to {self.db_url.split('@')[-1]}")

        connect_args = {}
        url = self.db_url

        if "neon.tech" in url and "+asyncpg" in url:
            connect_args["ssl"] = True

            # asyncpg doesn't accept sslmode in the URL - strip it.
            if "sslmode=require" in url:
                url = url.replace("?sslmode=require", "").replace(
                    "&sslmode=require", ""
                )

        self.engine = create_async_engine(
            url,
            echo=self.echo,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_timeout=self.pool_timeout,
            pool_recycle=self.pool_recycle,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        logger.info(
            f"Database pool: size={self.pool_size}, overflow={self.max_overflow}, "
            f"timeout={self.pool_timeout}s, recycle={self.pool_recycle}s"
        )

        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        logger.info("Database connection initialized")

    async def shutdown(self) -> None:
        if self.engine:
            logger.info("Closing database connections")
            await self.engine.dispose()
            logger.info("Database connections closed")

    async def create_database(self) -> None:
        """Create tables and (re-)apply idempotent RLS policies."""
        from app.infrastructure.persistence.models import Base

        if self.engine:
            logger.info("Creating database tables")
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created")

            await self._apply_rls()

    async def _apply_rls(self) -> None:
        """Apply RLS policy + enforcement SQL. Both files are idempotent."""
        import pathlib

        migrations_dir = (
            pathlib.Path(__file__).resolve().parent.parent.parent.parent
            / "scripts"
            / "migrations"
        )

        for sql_file in ["add_rls_policies.sql", "add_rls_enforcement.sql"]:
            sql_path = migrations_dir / sql_file
            if not sql_path.exists():
                logger.warning(f"RLS migration not found: {sql_path}")
                continue

            logger.info(f"Applying {sql_file}...")
            sql = sql_path.read_text()

            # Raw asyncpg connection: prepared-statement protocol can't run
            # multi-statement scripts, but driver_connection.execute can.
            assert self.engine is not None, "Database engine not initialized"
            async with self.engine.connect() as conn:
                raw_conn = await conn.get_raw_connection()
                driver_conn = raw_conn.driver_connection
                assert driver_conn is not None, "No driver connection available"
                await driver_conn.execute(sql)

            logger.info(f"Applied {sql_file}")

    def get_session_factory(self) -> "async_sessionmaker[AsyncSession]":
        """Return the session factory, raising if not yet initialized."""
        if self.session_factory is None:
            raise RuntimeError("Session factory not initialized")
        return self.session_factory

    async def get_session(self) -> AsyncSession:
        if not self.session_factory:
            self.init()

        if self.session_factory is None:
            raise RuntimeError("Session factory not initialized")

        session = self.session_factory()
        assert isinstance(
            session, AsyncSession
        ), "Session factory did not create an AsyncSession"
        return session


db = Database()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Plain session without RLS context.

    Use for unauthenticated endpoints, service accounts, or background tasks
    that handle their own authorization. Authenticated endpoints should use
    get_db_session_with_rls instead.
    """
    session = await db.get_session()
    try:
        yield session
    finally:
        await session.close()


async def get_db_session_with_rls(
    user: Dict[str, Any],
) -> AsyncGenerator[AsyncSession, None]:
    """Session with RLS context - sets app.current_org_id from the JWT.

    Intended as a FastAPI dependency (with `user = Depends(get_current_user)`).
    """
    session = await db.get_session()
    try:
        org_id = user.get("org_id")
        if org_id:
            # set_config(name, value, is_local=true) is session-scoped and works
            # with asyncpg's bind-parameter protocol; raw `SET` does not.
            await session.execute(
                text("SELECT set_config('app.current_org_id', :org_id, true)"),
                {"org_id": str(org_id)},
            )
            # logger.debug(f"RLS context set for org_id: {org_id}")
        else:
            logger.warning("No org_id in user context, RLS policies may block access")

        # Verify super_admin against the DB - JWT claims can be stale post-demotion.
        # Fail closed: any mismatch or error denies the privilege.
        if user.get("role") == "super_admin":
            user_id = user.get("id")
            if user_id:
                try:
                    result = await session.execute(
                        text("SELECT role FROM users WHERE id = :uid"),
                        {"uid": user_id},
                    )
                    row = result.first()
                    if row and row[0] == "super_admin":
                        await session.execute(
                            text(
                                "SELECT set_config('app.is_super_admin', 'true', true)"
                            )
                        )
                    else:
                        logger.warning(
                            f"JWT claims super_admin but DB role={row[0] if row else 'NOT_FOUND'} "
                            f"for user {user_id} - stale token or tampering"
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to verify super_admin for user {user_id}, "
                        f"denying privilege (fail closed): {e}"
                    )

        yield session
    finally:
        # Reset before returning to pool - prevents leakage between requests.
        try:
            await session.execute(text("RESET app.current_org_id"))
            await session.execute(text("RESET app.is_super_admin"))
        except Exception as e:
            logger.warning(f"Failed to reset RLS context: {e}")
        await session.close()


async def get_db_session_with_org(org_id: str) -> AsyncGenerator[AsyncSession, None]:
    """Session with RLS context for background work that has org_id but no user."""
    session = await db.get_session()
    try:
        await session.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": org_id},
        )
        yield session
    finally:
        try:
            await session.execute(text("RESET app.current_org_id"))
        except Exception as e:
            logger.warning(f"Failed to reset RLS context: {e}")
        await session.close()


async def get_db_session_service(
    caller: Optional[str] = None,
) -> AsyncGenerator[AsyncSession, None]:
    """Trusted-service session that bypasses RLS via app.is_service_account.

    Restricted to: worker endpoints, result processing, login/auth lookups,
    OAuth callbacks, public billing endpoints, webhook triggers. Do not use
    for normal authenticated endpoints.
    """
    if caller is None:
        import inspect

        try:
            frame = inspect.currentframe()
            outer = frame.f_back.f_back if frame and frame.f_back else None
            caller = (
                f"{outer.f_code.co_filename.split('/')[-1]}:{outer.f_code.co_name}"
                if outer
                else "unknown"
            )
        except Exception:
            caller = "unknown"

    session = await db.get_session()
    try:
        await session.execute(
            text("SELECT set_config('app.is_service_account', 'true', true)")
        )
        logger.debug(f"Service session opened by {caller}")
        yield session
    finally:
        try:
            await session.execute(text("RESET app.is_service_account"))
        except Exception as e:
            logger.warning(f"Failed to reset service-account context: {e}")
        await session.close()
