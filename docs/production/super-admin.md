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

## Related Docs

- [bootstrap.md](bootstrap.md) - bootstrap process, secrets, first boot sequence
- [env-vars.md](env-vars.md) - operator-tunable environment variables
