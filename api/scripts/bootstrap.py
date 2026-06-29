#!/usr/bin/env python3
"""
Bootstrap wrapper script for container startup.

This script:
1. Checks if system is already bootstrapped (via marker file)
2. Waits for database to be ready
3. Runs bootstrap_database.py to create super-org + super-admin
4. Creates marker file to prevent re-running

Runs automatically on container startup via docker-entrypoint.sh.
Env setup is handled by docker-entrypoint.sh or studio-init.sh.
"""

import os
import sys
import asyncio
from time import sleep

# Add project root to path
sys.path.insert(0, "/app")

# Load environment from /workspace/.env (symlinked to /app/.env by entrypoint)
from dotenv import load_dotenv

load_dotenv("/workspace/.env", override=False)

BOOTSTRAP_MARKER = "/workspace/.bootstrapped"
REQUIRED_SECRETS = [
    "SHS_JWT_SECRET_KEY",
    "SHS_WORKER_SHARED_SECRET",
    "SHS_CREDENTIAL_ENCRYPTION_KEY",
]


def _read_dotenv_keys(path: str) -> dict[str, str]:
    """Read key=value pairs from a .env file without modifying os.environ."""
    result = {}
    if not os.path.exists(path):
        return result
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def _append_to_dotenv(path: str, key: str, value: str):
    """Append a key=value to the .env file."""
    with open(path, "a") as f:
        f.write(f"\n{key}={value}\n")  # codeql[py/clear-text-storage-sensitive-data]


_FERNET_KEY_GEN_HINT = (
    'Generate with: python -c "from cryptography.fernet import Fernet; '
    'print(Fernet.generate_key().decode())"'
)


def _validate_fernet_key(key: str) -> None:
    """Raise ValueError if key isn't a valid Fernet key.

    Format check fails fast at startup so operators see a clear message
    instead of a cryptic mid-request crash on the first credential write.
    """
    from cryptography.fernet import Fernet

    Fernet(key.encode())


def validate_secrets():
    """Validate required secrets, recovering from env vars when possible.

    Flow for each secret:
    1. In .env - use it, done.
    2. In os.environ (RunPod vault, shell env) - write to .env for persistence, continue.
    3. Not found anywhere - fail with context-aware message.

    SHS_CREDENTIAL_ENCRYPTION_KEY also gets a Fernet-format check so an
    operator who pasted a hex string (or any non-Fernet value) fails here
    rather than later inside CredentialEncryption.
    """
    env_file = "/workspace/.env"
    dotenv_keys = _read_dotenv_keys(env_file)
    has_bootstrapped = os.path.exists(BOOTSTRAP_MARKER)
    missing = []

    for key in REQUIRED_SECRETS:
        # Already in .env with a value
        if dotenv_keys.get(key):
            continue

        # Not in .env, but in process environment (vault, shell, etc.)
        env_value = os.getenv(key)
        if env_value:
            _append_to_dotenv(env_file, key, env_value)
            print(f"✅ {key} found in environment, written to .env")  # codeql[py/clear-text-logging-sensitive-data]
            continue

        missing.append(key)

    if missing:
        # Context-aware error message
        lines = [f"❌ Required secrets not set: {', '.join(missing)}"]
        if has_bootstrapped:
            if "SHS_CREDENTIAL_ENCRYPTION_KEY" in missing:
                lines.append("")
                lines.append("⚠️  SHS_CREDENTIAL_ENCRYPTION_KEY was previously set.")
                lines.append(
                    "   Existing encrypted credentials are unreadable without the original key."
                )
                lines.append("   Restore the original key from your backup to recover.")
            lines.append("")
            lines.append(
                "Add missing keys to /workspace/.env or set them as environment variables."
            )
        else:
            lines.append(_FERNET_KEY_GEN_HINT)

        raise RuntimeError("\n".join(lines))

    # All required secrets are present. Fernet-format check on the encryption
    # key catches operators who pasted a hex string or other non-Fernet value.
    encryption_key = dotenv_keys.get("SHS_CREDENTIAL_ENCRYPTION_KEY") or os.getenv(
        "SHS_CREDENTIAL_ENCRYPTION_KEY", ""
    )
    try:
        _validate_fernet_key(encryption_key)
    except Exception as e:
        raise RuntimeError(
            "\n".join(
                [
                    f"❌ SHS_CREDENTIAL_ENCRYPTION_KEY is not a valid Fernet key: {e}",
                    "   Fernet requires 32 random bytes, urlsafe-base64-encoded (44 chars ending in '=').",
                    f"   {_FERNET_KEY_GEN_HINT}",
                    "",
                    "   ⚠️  Replacing this key makes existing encrypted credentials unreadable.",
                ]
            )
        ) from e


async def wait_for_database():
    """Wait for database to be ready (60 seconds total)."""
    import asyncpg

    print("⏳ Waiting for database...")

    # Get database URL from environment and convert to asyncpg format
    db_url = os.getenv("SHS_DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("SHS_DATABASE_URL is required and not set")
    db_url = db_url.replace("+asyncpg", "")

    for i in range(30):
        try:
            conn = await asyncpg.connect(db_url)
            await conn.execute("SELECT 1")
            await conn.close()
            print("✅ Database ready")
            return True
        except Exception as e:
            if i == 29:
                raise Exception("Database not ready after 60 seconds") from e
            sleep(2)


async def _has_alembic_version_table(db_url: str) -> bool:
    import asyncpg

    conn = await asyncpg.connect(db_url)
    try:
        row = await conn.fetchrow(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'alembic_version'"
        )
        return row is not None
    finally:
        await conn.close()


async def _has_any_app_tables(db_url: str) -> bool:
    """Detect a brownfield DB: tables exist but no alembic_version row."""
    import asyncpg

    conn = await asyncpg.connect(db_url)
    try:
        row = await conn.fetchrow(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN ('users', 'organizations') "
            "LIMIT 1"
        )
        return row is not None
    finally:
        await conn.close()


def _run_alembic(*args: str) -> None:
    """Run alembic CLI. Failures emit a distinctive log line operators / studio-console
    can grep for: '❌ ALEMBIC MIGRATION FAILED'."""
    import subprocess

    api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cmd = ["alembic", *args]
    print(f"📋 Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=api_dir, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        # Single-line, grep-friendly marker for log scrapers / console diagnostics.
        # Includes the alembic subcommand so operators can see WHICH operation failed.
        print(
            f"❌ ALEMBIC MIGRATION FAILED: alembic {' '.join(args)} "
            f"(exit {result.returncode}). See preceding output for the failing revision.",
            file=sys.stderr,
        )
        raise Exception(f"alembic {' '.join(args)} failed (exit {result.returncode})")
    print(result.stdout)


def _discover_major_baselines(
    _scan_dirs: list[str] | None = None,
) -> dict[int, str]:
    """Return {major_version: revision_id} by scanning for *_vN_baseline*.py files.

    Scans two directories:
    - alembic/versions/     : active chain (current-major baseline lives here)
    - alembic/baseline_markers/ : archive (prior-major baselines after squash)
    """
    import re

    if _scan_dirs is None:
        api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _scan_dirs = [
            os.path.join(api_dir, "alembic", "versions"),
            os.path.join(api_dir, "alembic", "baseline_markers"),
        ]
    pattern = re.compile(r"^([0-9a-f]+)_v(\d+)_baseline")
    baselines: dict[int, str] = {}
    for scan_dir in _scan_dirs:
        if not os.path.isdir(scan_dir):
            continue
        for filename in os.listdir(scan_dir):
            m = pattern.match(filename)
            if m:
                baselines[int(m.group(2))] = m.group(1)
    return baselines


def _check_major_version_compatibility(
    db_revision: str,
    _baselines: dict[int, str] | None = None,
    _known_revisions: set[str] | None = None,
) -> None:
    """Exit 1 if db_revision is from a prior major or is unrecognized.

    Compatible  : db_revision is in the current chain (known_revisions).
    Prior-major : db_revision exactly matches a historical major baseline marker.
    Unknown     : db_revision is neither — newer version or corrupted stamp.
    """
    if _baselines is None:
        _baselines = _discover_major_baselines()
    if not _baselines:
        return

    if _known_revisions is None:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg = Config(os.path.join(api_dir, "alembic.ini"))
        script_dir = ScriptDirectory.from_config(cfg)
        _known_revisions = {s.revision for s in script_dir.walk_revisions()}

    if db_revision in _known_revisions:
        return

    current_major = max(_baselines)
    for major, rev in _baselines.items():
        if major < current_major and db_revision == rev:
            print(
                f"\nFATAL: Studio cannot start.\n\n"
                f"The database was migrated by an incompatible major version of Studio.\n"
                f"  Database schema: v{major} (revision {db_revision})\n"
                f"  Running code:    v{current_major}\n\n"
                f"Run the Studio v{major}→v{current_major} upgrade tool before starting this version:\n"
                f"  https://docs.selfhosthub.com/upgrading/v{major}-to-v{current_major}\n\n"
                f"To downgrade, reinstall the Studio v{major} image.\n"
            )
            sys.exit(1)

    print(
        f"\nFATAL: Studio cannot start.\n\n"
        f"The database contains an unrecognized schema revision: {db_revision}\n\n"
        f"This usually means the database was migrated by a newer version of Studio\n"
        f"than the one you are running, or the alembic_version table is corrupted.\n\n"
        f"See: https://docs.selfhosthub.com/upgrading\n"
    )
    sys.exit(1)


async def _read_db_revision(db_url: str) -> str | None:
    """Return the stamped revision from alembic_version, or None if the table is empty."""
    import asyncpg

    conn = await asyncpg.connect(db_url)
    try:
        row = await conn.fetchrow("SELECT version_num FROM alembic_version LIMIT 1")
        return row[0] if row else None
    finally:
        await conn.close()


async def _ensure_pgvector(db_url: str) -> None:
    """Create the pgvector extension if missing, then upgrade it in place.

    Must run BEFORE `alembic upgrade head`: the baseline migration creates
    columns of type `Vector`, which fails if the extension is absent. Both
    statements are idempotent - `CREATE EXTENSION IF NOT EXISTS` is a no-op
    when present, and `ALTER EXTENSION ... UPDATE` is a no-op when already at
    the binary's bundled version.

    The ALTER is how existing installs migrate: after an image upgrade ships a
    newer pgvector, a `/workspace` DB still records the old extension version
    (CREATE never upgrades an already-present extension). This runs on every
    boot for every shape, so the on-disk extension follows the binary.
    """
    import asyncpg

    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        await conn.execute("ALTER EXTENSION vector UPDATE;")
        print("✅ pgvector extension ready")
    finally:
        await conn.close()


async def _ensure_toast_compression(db_url: str) -> None:
    """Default new TOASTed values to LZ4 (faster than pglz at ~the same size).

    The GUC is read at row-write time, so every value written after this gets
    LZ4; existing rows keep their prior method until rewritten. ALTER SYSTEM
    persists the setting across restarts and pg_reload_conf applies it without
    one. Best-effort by design - a compression default must never block startup:
    managed providers (e.g. Neon) forbid ALTER SYSTEM, and a build without LZ4
    rejects the value; both are warnings, not fatal. The SHOW confirms the
    binary actually supports LZ4.
    """
    import asyncpg

    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute("ALTER SYSTEM SET default_toast_compression = 'lz4';")
        await conn.execute("SELECT pg_reload_conf();")
        active = await conn.fetchval("SHOW default_toast_compression;")
        if active == "lz4":
            print("✅ TOAST compression: lz4")
        else:
            print(f"⚠️  TOAST compression is '{active}', expected lz4")
    except Exception as e:
        print(f"⚠️  Could not set lz4 TOAST compression (continuing with default): {e}")
    finally:
        await conn.close()


async def ensure_schema():
    """Apply schema migrations + RLS.

    Brownfield path: existing DB with tables but no alembic_version row gets
    stamped at head before subsequent migrations. Fresh DB and already-managed
    DBs both go through `upgrade head`.
    """
    db_url = os.getenv("SHS_DATABASE_URL", "").replace("+asyncpg", "")

    # pgvector must exist before alembic runs (baseline creates Vector columns).
    await _ensure_pgvector(db_url)

    # Prefer LZ4 for new TOASTed values; best-effort, never blocks startup.
    await _ensure_toast_compression(db_url)

    has_version_table = await _has_alembic_version_table(db_url)
    if has_version_table:
        db_revision = await _read_db_revision(db_url)
        if db_revision is not None:
            _check_major_version_compatibility(db_revision)

    if not has_version_table and await _has_any_app_tables(db_url):
        print(
            "📋 Brownfield DB detected (tables present, no alembic_version) - stamping head"
        )
        _run_alembic("stamp", "head")
    else:
        print("📋 Applying alembic migrations...")
        _run_alembic("upgrade", "head")

    # RLS policies are idempotent; re-apply on every boot.
    from scripts.create_tables import apply_rls

    print("📋 Applying RLS policies...")
    success = await apply_rls()
    if not success:
        raise Exception("Failed to apply RLS policies")
    return True


async def run_bootstrap():
    """Run the bootstrap process."""
    env = os.getenv("SHS_ENV")
    if not env:
        raise RuntimeError("SHS_ENV is required and not set")

    # Always validate secrets - even after bootstrap.
    # Catches missing keys from .env edits or accidental deletion.
    if env == "production":
        validate_secrets()

    print("🚀 Starting bootstrap process...")

    # Wait for database
    await wait_for_database()

    # Schema migrations run on every boot (alembic is idempotent). The marker
    # file only gates super-org / super-admin creation below.
    await ensure_schema()

    # Production only: marker file prevents re-creating super-org/super-admin
    # on shared storage (multi-instance Kubernetes/RunPod). Dev always re-runs.
    if env == "production" and os.path.exists(BOOTSTRAP_MARKER):
        print("✅ System already bootstrapped (marker file exists)")
        return

    # Import and run the existing bootstrap_database script
    from scripts.bootstrap_database import bootstrap as db_bootstrap

    try:
        # Phase 1: create tables + org (never crashes, no admin needed)
        await db_bootstrap()

        # Only create marker if admin exists (phase 2 completed)
        import asyncpg

        db_url = os.getenv("SHS_DATABASE_URL", "").replace("+asyncpg", "")
        conn = await asyncpg.connect(db_url)
        admin = await conn.fetchrow(
            "SELECT id FROM users WHERE role = 'super_admin' LIMIT 1"
        )
        await conn.close()

        if admin:
            with open(BOOTSTRAP_MARKER, "w") as f:
                f.write("bootstrapped\n")
            print(f"✅ Bootstrap marker created: {BOOTSTRAP_MARKER}")
        else:
            print("⏳ Waiting for admin account - run Services → Start All")

    except Exception as e:
        print(f"❌ Bootstrap failed: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    try:
        asyncio.run(run_bootstrap())
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal error during bootstrap: {e}", file=sys.stderr)
        sys.exit(1)
