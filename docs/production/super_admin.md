# Super Admin Guide

> **Community & support:** [SelfHostHub Community](https://www.skool.com/selfhosthub) · [Innovators (Plus)](https://www.skool.com/selfhostinnovators)

> **Audience:** Operators who deploy and manage a Studio instance.

---

## Account Details

Bootstrap creates the super admin account on first boot:

| Field | Value | Source |
|-------|-------|--------|
| Username | `super_admin` | Hardcoded |
| Email | Operator-provided | `SHS_ADMIN_EMAIL` env var or quickstart prompt |
| Password | Operator-provided | `SHS_ADMIN_PASSWORD` env var or quickstart prompt |
| Role | `super_admin` | Hardcoded |
| Organization | System Organization | Created by bootstrap |

The username is always `super_admin` - it cannot be changed during setup. Log in with your email and password.

---

## What Super Admin Can Do

The super admin has full platform control. These capabilities are exclusive to the `super_admin` role - org admins cannot access them.

### Provider & Package Management

- Install, update, and remove provider packages
- Upload packages from zip, URL, or local path
- Refresh provider/service definitions from package files
- Install all packages from the marketplace catalog
- View original package defaults vs. customized values

### Organization Lifecycle

- List all organizations with stats
- Activate, suspend, or set organizations to pending approval
- Manage org admin accounts (activate/deactivate)
- Access any organization's data for support (read-only)

### Billing & Limits

- Update subscription status
- View billing summaries for any organization
- Override, revert, and reset organization limits
- Propagate plan changes to all subscriptions
- Monitor grace periods and enforce expirations

### Marketplace Catalogs

- Upload and refresh catalogs for workflows, prompts, blueprints, and ComfyUI
- View raw catalog data

### System Infrastructure

- View system health (WebSocket, storage, workers, database)
- View storage usage across all organizations
- Monitor worker heartbeats and deregister workers
- Enable/disable maintenance mode with user-facing warnings

### Audit & Compliance

- View system-level audit events (not scoped to any organization)
- View audit events across all organizations
- Export audit logs as JSONL for SIEM ingestion

### Site Content

- Edit all public-facing content: hero, features, testimonials, about, terms, privacy, contact
- Configure page visibility, registration settings, and compliance disclosures

### Documentation

- Access super admin infrastructure guide via API

---

## What Super Admin Cannot Do

- Change the `super_admin` username after creation
- Bypass credential encryption (`SHS_CREDENTIAL_ENCRYPTION_KEY` is required)
- Re-run bootstrap on a production system without removing the `.bootstrapped` marker

---

## First Login Checklist

After the stack is up:

1. Open the UI at `http://localhost:3000` (or your configured URL)
2. Log in with your email and the password you set during setup
3. Verify the System Organization exists
4. Configure the **Entitlement Token** (Settings → Secrets) to unlock advanced providers and workflows from the Plus catalog. Get your token at [SelfHostHub Community](https://www.skool.com/selfhostinnovators). A dashboard banner will remind you if this is unconfigured.
5. Add provider credentials for any providers you plan to use (Settings → Providers)
6. Back up `~/.studio/.env` - losing `SHS_CREDENTIAL_ENCRYPTION_KEY` makes stored credentials unrecoverable

---

## Password Reset

If you lose the super admin password, use the reset script inside the API container. In a production environment (`SHS_ENV=production`) you must pass `SHS_FORCE_PRODUCTION=true` to bypass the safety check.

**Interactive** (prompts for the new password):

```bash
docker compose exec -e SHS_FORCE_PRODUCTION=true api python scripts/reset_admin_password.py
```

**Non-interactive** (supply password via env var):

```bash
docker compose exec \
  -e SHS_FORCE_PRODUCTION=true \
  -e SHS_ADMIN_PASSWORD=<new-password> \
  api python scripts/reset_admin_password.py
```

Password requirements (enforced by the script): 8–72 characters, at least one uppercase letter, one lowercase letter, one digit, and one special character (`!@#$%^&*` etc.).

---

## Major Version Upgrades

When you upgrade Studio to a new major version (e.g., v1 → v2), the API checks the database schema version at startup. If the schema was migrated by a prior major and hasn't been upgraded yet, the API refuses to start and prints instructions to stdout. This protects against running incompatible code against a stale schema — the failure is loud and early rather than silent data corruption later.

### Error messages

**Prior-major schema (expected upgrade case):**

```
FATAL: Studio cannot start.

The database was migrated by an incompatible major version of Studio.
  Database schema: v1 (revision 9f01e7ae15f2)
  Running code:    v2

Run the Studio v1→v2 upgrade tool before starting this version:
  https://docs.selfhosthub.com/upgrading/v1-to-v2

To downgrade, reinstall the Studio v1 image.
```

**Unrecognized revision (DB is from a newer version, or corrupted):**

```
FATAL: Studio cannot start.

The database contains an unrecognized schema revision: <revision>

This usually means the database was migrated by a newer version of Studio
than the one you are running, or the alembic_version table is corrupted.

See: https://docs.selfhosthub.com/upgrading
```

### What to do

- **Prior-major error:** go to [https://docs.selfhosthub.com/upgrading/](https://docs.selfhosthub.com/upgrading/) and find the upgrade guide for your version transition. Run the upgrade tool documented there, then restart Studio — the guardrail will pass and the API will start normally.
- **To downgrade instead:** reinstall the previous major's image. Do not run the new image against the old schema.
- **Unrecognized revision:** you are likely running an older image against a DB that was already migrated by a newer one. Upgrade the image to match, or restore a backup from before the migration.

### Backups from a prior major version

When restoring a backup taken under a prior major version, the same guardrail fires on restart. Restore the database, run the major-version upgrade tool, then start the API. Do not try to bypass the guardrail by manually stamping `alembic_version` — the schema and code will diverge and fail in worse ways later.

### Upgrade tool index

Each major boundary ships its own upgrade command. The canonical index of available upgrade paths is at [https://docs.selfhosthub.com/upgrading/](https://docs.selfhosthub.com/upgrading/). Upgrade tooling for v2 will be documented there when v2 ships.

---

## Related Docs

- [bootstrap.md](bootstrap.md) - bootstrap process, secrets, first boot sequence
- [env-vars.md](env-vars.md) - operator-tunable environment variables
- [https://docs.selfhosthub.com/upgrading/](https://docs.selfhosthub.com/upgrading/) - major-version upgrade paths
