# api/app/infrastructure/persistence/database.py

"""DB connection and session management with optional RLS for org isolation."""

import logging
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def __getattr__(name: str):
    """Lazy module-level URLs — resolved on first read so importing this
    module (e.g. from Alembic's env.py via the package __init__)
    doesn't trigger full Settings validation.

    DATABASE_URL is the privileged string (bootstrap/Alembic/seeding);
    RUNTIME_DATABASE_URL is what serves requests (restricted shs_app role
    when DATABASE_APP_URL is set, else the same privileged string).
    """
    if name == "DATABASE_URL":
        return get_settings().DATABASE_URL
    if name == "RUNTIME_DATABASE_URL":
        s = get_settings()
        return s.DATABASE_APP_URL or s.DATABASE_URL
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
        # Request serving prefers the restricted-role URL (DATABASE_APP_URL);
        # bootstrap/Alembic/seeding keep the privileged DATABASE_URL.
        s = get_settings()
        self.db_url = self._db_url_override or s.DATABASE_APP_URL or s.DATABASE_URL
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

    def get_service_session_factory(self) -> "async_sessionmaker[AsyncSession]":
        """Session factory whose sessions carry trusted-service posture.

        For background surfaces (result processing, cleanup/schedule tasks)
        that operate across orgs: every session is primed so the RLS
        service-bypass policies pass once the runtime role stops being a
        superuser.
        """
        from typing import cast

        from app.infrastructure.persistence.rls_posture import (
            prime_service_posture,
        )

        base_factory = self.get_session_factory()

        def factory(*args, **kwargs) -> AsyncSession:
            session = base_factory(*args, **kwargs)
            prime_service_posture(session)
            return session

        return cast("async_sessionmaker[AsyncSession]", factory)

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

    Use for unauthenticated endpoints or background tasks that handle their
    own authorization. Authenticated endpoints attach org posture to this
    same session via get_db_session_rls (presentation dependencies).
    """
    session = await db.get_session()
    try:
        yield session
    finally:
        await session.close()


async def get_db_session_service(
    caller: Optional[str] = None,
) -> AsyncGenerator[AsyncSession, None]:
    """Trusted-service session that bypasses RLS via app.is_service_account.

    Restricted to: worker endpoints, result processing, login/auth lookups,
    OAuth callbacks, public billing endpoints, webhook triggers. Do not use
    for normal authenticated endpoints.
    """
    from app.infrastructure.persistence.rls_posture import set_service_posture

    session = await db.get_session()
    try:
        await set_service_posture(session)
        yield session
    finally:
        await session.close()
