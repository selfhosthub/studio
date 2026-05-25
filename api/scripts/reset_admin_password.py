#!/usr/bin/env python3
"""
Reset Super Admin Password - Emergency Password Reset

This script allows you to reset the super admin password when locked out.
Uses the same validation and hashing as the bootstrap script.
"""

import asyncio
import getpass
import logging
import os
import sys
from datetime import UTC, datetime

import asyncpg
from dotenv import load_dotenv

# Add parent directory to path to import validation
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import password validation and production safety from bootstrap
from scripts.bootstrap_database import validate_password
from scripts.check_production_safety import check_production_safety
from app.infrastructure.auth.password import hash_password

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("reset-password")

# Production safety check
if not check_production_safety(allow_override=True):
    logger.error("Production safety check failed - aborting")
    sys.exit(1)


def prompt_for_new_password() -> str:
    """Prompt for new admin password with validation."""
    print("\n" + "=" * 70)
    print("🔐 Reset Super Admin Password")
    print("=" * 70)
    print("")
    print("Password requirements:")
    print("   - 8-72 characters (bcrypt limitation)")
    print("   - Must contain:")
    print("     • At least one uppercase letter")
    print("     • At least one lowercase letter")
    print("     • At least one digit")
    print("     • At least one special character (!@#$%^&*...)")
    print("")

    while True:
        password = getpass.getpass("   New password: ")
        if not password:
            print("   ❌ Password cannot be empty")
            continue

        # Validate password
        is_valid, message = validate_password(password)
        if not is_valid:
            print(f"   ❌ {message}")
            continue

        # Confirm password
        confirm = getpass.getpass("   Confirm password: ")
        if password != confirm:
            print("   ❌ Passwords do not match. Please try again.")
            continue

        return password


async def reset_admin_password(password: str):
    """Reset the super admin password in the database."""
    # Load environment
    load_dotenv()

    database_url = os.getenv("SHS_DATABASE_URL")
    if not database_url:
        raise ValueError("SHS_DATABASE_URL not found in environment")

    # Parse asyncpg connection string (strip +asyncpg if present)
    if "+asyncpg://" in database_url:
        database_url = database_url.replace("+asyncpg://", "://")
    elif "postgresql://" not in database_url:
        raise ValueError(f"Invalid DATABASE_URL format: {database_url}")

    print("\n🔄 Connecting to database...")
    conn = await asyncpg.connect(database_url)

    try:
        # Find the super admin user
        print("🔍 Looking for super admin user...")
        admin = await conn.fetchrow(
            "SELECT id, username, email, role FROM users WHERE role = 'super_admin' LIMIT 1"
        )

        if not admin:
            print("\n❌ Error: No super admin user found in database!")
            print("")
            print("   This script can only reset the super admin password.")
            print("   If you don't have a super admin, run: make bootstrap")
            return False

        print(f"✅ Found super admin: {admin['username']} ({admin['email']})")
        print("")

        # Hash the new password
        print("🔒 Hashing new password...")
        hashed = hash_password(password)

        # Update the password
        print("💾 Updating password in database...")
        await conn.execute(
            """
            UPDATE users
            SET hashed_password = $1, updated_at = $2
            WHERE id = $3
            """,
            hashed,
            datetime.now(UTC),
            admin["id"],
        )

        print("")
        print("=" * 70)
        print("✅ SUCCESS: Super admin password has been reset!")
        print("=" * 70)
        print("")
        print(f"   Username: {admin['username']}")
        print(f"   Email:    {admin['email']}")
        print("")
        print("   You can now log in with the new password.")
        print("")
        return True

    except Exception as e:
        print(f"\n❌ Error resetting password: {e}")
        return False
    finally:
        await conn.close()


async def main():
    """Main entry point."""
    try:
        # Check for non-interactive mode (Docker)
        admin_password = os.getenv("SHS_ADMIN_PASSWORD")

        if admin_password:
            # Password provided via env var
            is_valid, error = validate_password(admin_password)
            if not is_valid:
                logger.error(f"❌ Invalid SHS_ADMIN_PASSWORD: {error}")
                sys.exit(1)
            new_password = admin_password
        else:
            # Interactive mode - prompt for new password
            new_password = prompt_for_new_password()

        # Reset the password
        success = await reset_admin_password(new_password)

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\n❌ Password reset cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
