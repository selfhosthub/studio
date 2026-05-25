# api/scripts/bootstrap_database.py

"""
Database bootstrap script.

Creates the System Organization and Super Admin user required for the
application to function. Supports interactive (TTY), environment-variable,
and dev/e2e auto-credential modes. Uses SQLAlchemy ORM models directly.
"""

import asyncio
import os
import sys
import uuid
import logging
import getpass

from dotenv import load_dotenv

# Load environment variables BEFORE importing app modules.
# .env.local holds secrets (SHS_ENTITLEMENT_TOKEN, API keys) that override
# the base .env. Before 9a89696 this happened implicitly via the seeders
# import; after that import was removed, .env.local was no longer loaded.
# Candidate paths: Docker workspace, Docker envs mount, host dev.
load_dotenv("/workspace/.env")
load_dotenv()
load_dotenv("/workspace/.env.local", override=True)
load_dotenv("/app/envs/.env.local", override=True)
load_dotenv(
    os.path.join(os.path.dirname(__file__), "..", "envs", ".env.local"), override=True
)

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import the application's password hashing function
from app.infrastructure.auth.password import hash_password

# Import workspace utilities
from app.infrastructure.storage.workspace import ensure_org_workspace

# Import ORM models
from app.infrastructure.persistence.models import (
    OrganizationModel,
    OrganizationSecretModel,
    UserModel,
)

# SQLAlchemy
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.infrastructure.persistence.database import DATABASE_URL

# Session factory with service account RLS bypass (inlined from seeders.lib.db)
_engine = None
_session_factory = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_async_engine(DATABASE_URL, echo=False)

        @event.listens_for(_engine.sync_engine, "connect")
        def _set_service_account(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("SELECT set_config('app.is_service_account', 'true', false)")
            cursor.close()

        _session_factory = async_sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


async def dispose_engine():
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("bootstrap")


def validate_password(password: str) -> tuple[bool, str]:
    """
    Validate password strength.

    Returns:
        tuple: (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if len(password) > 72:
        return False, "Password cannot be longer than 72 characters (bcrypt limitation)"

    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)

    if not (has_upper and has_lower and has_digit and has_special):
        return (
            False,
            "Password must contain uppercase, lowercase, digit, and special character",
        )

    return True, ""


def prompt_for_password(username: str, allow_skip: bool = False) -> str | None:
    """
    Prompt user for a password with validation.

    Args:
        username: Username for context in prompt
        allow_skip: If True, allow empty password (for demo user)

    Returns:
        str: The validated password
    """
    while True:
        print(f"\n🔐 Set password for user '{username}':")
        print("   Requirements: 8+ chars, uppercase, lowercase, digit, special char")

        if allow_skip:
            print("   (Press Enter to skip)")

        password = getpass.getpass("   Password: ")

        if allow_skip and not password:
            return None

        # Validate password
        is_valid, error = validate_password(password)
        if not is_valid:
            print(f"   ❌ {error}")
            continue

        # Confirm password
        password_confirm = getpass.getpass("   Confirm password: ")

        if password != password_confirm:
            print("   ❌ Passwords do not match")
            continue

        return password


async def create_super_admin(
    session: AsyncSession, admin_password: str, admin_email: str, org_id: uuid.UUID
) -> uuid.UUID:
    """Create a super admin user if one doesn't exist."""
    logger.info("Checking for existing super admin...")

    result = await session.execute(
        select(UserModel).where(UserModel.role == "super_admin").limit(1)
    )
    existing = result.scalar_one_or_none()

    if existing:
        logger.info(f"✅ Super admin already exists: {existing.email}")
        return existing.id

    # Create super admin
    logger.info("Creating super admin user...")
    admin = UserModel(
        username="super_admin",
        email=admin_email,
        hashed_password=hash_password(admin_password),
        role="super_admin",
        is_active=True,
        first_name="System",
        last_name="Administrator",
        organization_id=org_id,
    )
    session.add(admin)
    await session.flush()

    logger.info(f"✅ Super admin created with ID: {admin.id}")
    return admin.id


async def create_super_organization(session: AsyncSession) -> uuid.UUID:
    """Create a super organization if one doesn't exist."""
    logger.info("Checking for existing super organization...")

    result = await session.execute(
        select(OrganizationModel).where(OrganizationModel.slug == "system").limit(1)
    )
    existing = result.scalar_one_or_none()

    if existing:
        logger.info(f"✅ Super organization already exists: {existing.name}")
        return existing.id

    # Create super organization
    logger.info("Creating super organization...")
    org = OrganizationModel(
        name="System Organization",
        slug="system",
        description="System-level organization for administrators",
        settings={
            "is_system": True,
            "can_create_organizations": True,
            "max_workflows": -1,
            "branding": {
                "company_name": "Self-Host Studio",
                "short_name": "Studio",
                "tagline": "Build, run, and manage automated workflows.",
                "primary_color": "#3B82F6",
                "secondary_color": "#10B981",
                "accent_color": "#F59E0B",
                "hero_gradient_start": "#2563EB",
                "hero_gradient_end": "#4F46E5",
                "header_background": "#FFFFFF",
                "header_text": "#3B82F6",
                "section_background": "#F9FAFB",
            },
        },
    )
    session.add(org)
    await session.flush()

    logger.info(f"✅ Super organization created with ID: {org.id}")

    # Create workspace directories for the organization
    logger.info("Creating workspace directories...")
    ensure_org_workspace(org.id, name="System Organization", slug="system")
    logger.info("✅ Workspace directories created")

    return org.id


async def create_entitlement_token_secret(
    session: AsyncSession, admin_id: uuid.UUID, org_id: uuid.UUID
) -> None:
    """Create a protected ENTITLEMENT_TOKEN secret if one doesn't exist.

    The token gives access to the Plus catalog (advanced providers/workflows).
    If SHS_ENTITLEMENT_TOKEN is set in the environment,
    the secret is created pre-populated and active. Otherwise a blank placeholder
    is created for the super-admin to configure later via the dashboard.
    """
    result = await session.execute(
        select(OrganizationSecretModel).where(
            OrganizationSecretModel.organization_id == org_id,
            OrganizationSecretModel.name == "ENTITLEMENT_TOKEN",
        )
    )
    if result.scalar_one_or_none():
        logger.info("ENTITLEMENT_TOKEN secret already exists, skipping")
        return

    token_value = os.getenv("SHS_ENTITLEMENT_TOKEN")
    secret = OrganizationSecretModel(
        id=uuid.uuid4(),
        organization_id=org_id,
        name="ENTITLEMENT_TOKEN",
        secret_type="bearer",
        secret_data={"token": token_value} if token_value else {},
        description=(
            "Get your token from the SelfHostHub Community"
            " (https://www.skool.com/selfhostinnovators)"
            " to access advanced providers and workflows."
        ),
        is_active=bool(token_value),
        is_protected=True,
        created_by=admin_id,
    )
    session.add(secret)
    await session.flush()

    status = "with token" if token_value else "placeholder"
    logger.info(f"Created ENTITLEMENT_TOKEN secret ({status})")


async def bootstrap():
    """Run the bootstrap process."""
    # Check if running in development/e2e mode (auto-credentials)
    is_dev_mode = os.getenv("SHS_DEBUG", "false").lower() == "true"
    is_e2e_mode = os.getenv("SHS_ENV", "").lower() == "e2e"
    mode_name = "E2E" if is_e2e_mode else "DEVELOPMENT" if is_dev_mode else "PRODUCTION"

    # Check for non-interactive mode (used by Docker/CI/Dev)
    admin_password = os.getenv("SHS_ADMIN_PASSWORD")
    admin_email = os.getenv("SHS_ADMIN_EMAIL", "admin@example.com")

    if admin_password:
        # Non-interactive mode (Docker/CI/Dev)
        logger.info("Running in non-interactive mode (using environment variables)")

        # Validate admin password
        is_valid, error = validate_password(admin_password)
        if not is_valid:
            logger.error(f"❌ Invalid SHS_ADMIN_PASSWORD: {error}")
            sys.exit(1)
    elif is_dev_mode or is_e2e_mode:
        # Development/E2E mode - use default password (insecure but convenient)
        logger.info(f"🔧 Running in {mode_name} mode - using default password")
        logger.warning("⚠️  Default password: Admin123!")
        logger.warning("⚠️  DO NOT use this in production!")
        admin_password = "Admin123!"
        admin_email = "admin@example.com"
    else:
        # No credentials provided - create tables and org only.
        logger.info("No admin credentials - creating tables and org only")

        session_factory = get_session_factory()
        async with session_factory() as session:
            await create_super_organization(session)
            await session.commit()
        await dispose_engine()

        print("✅ Database ready - waiting for admin account setup")
        return

    print("\n" + "-" * 70)
    print("🔄 Connecting to database and creating super admin...")
    print("-" * 70)

    logger.info("Starting application bootstrap...")

    # Use SQLAlchemy session factory
    logger.info("Connecting to database...")
    session_factory = get_session_factory()

    async with session_factory() as session:
        # Create initial data in correct order:
        # 1. Create system organization first (users need org_id)
        # 2. Create super admin user with that org_id (if credentials provided)
        # 3. Create protected ENTITLEMENT_TOKEN secret (if admin created)
        org_id = await create_super_organization(session)

        if admin_password and admin_email:
            admin_id = await create_super_admin(
                session, admin_password, admin_email, org_id
            )
            await create_entitlement_token_secret(session, admin_id, org_id)
        else:
            logger.info("No admin credentials - skipping admin creation")

        await session.commit()

    await dispose_engine()

    print("\n" + "=" * 70)
    print("✅ Bootstrap completed successfully!")
    print("=" * 70)
    print("\n📋 Created:")
    print("   • System Organization (slug: system)")
    if admin_password and admin_email:
        print(f"   • Super Admin: {admin_email} (username: super_admin)")
        print("   • ENTITLEMENT_TOKEN secret (configure in Settings → Secrets)")

    # Show password in dev/e2e mode only
    if is_dev_mode or is_e2e_mode:
        print(f"\n🔧 {mode_name} Mode Credentials:")
        print("   • Admin password: Admin123!")
        print("   ⚠️  This is a DEFAULT password - not for production!")

    api_base = os.environ.get("SHS_API_BASE_URL", "http://localhost:8000")
    print("\n📍 Next Steps:")
    print(f"   • API Documentation: {api_base}/docs")
    print(f"   • API Health Check: {api_base}/health")

    if not is_dev_mode and not is_e2e_mode:
        print("\n🔐 Security Reminders:")
        print("   • Store your password securely")
        print("   • Change password via API if needed")
        print("   • Review ~/workspace for organization data")
    print("")

    logger.info("Database connection closed")


if __name__ == "__main__":
    # Run bootstrap process
    asyncio.run(bootstrap())
