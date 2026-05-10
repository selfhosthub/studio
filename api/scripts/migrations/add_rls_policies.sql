-- RLS (Row-Level Security) Policies for Multi-Tenant Isolation
--
-- This migration enables RLS on all organization-scoped tables.
-- Policies use the session variable 'app.current_org_id' set by the application.
--
-- Two access modes:
--   1. Org-scoped: app.current_org_id is set → queries filtered to that org
--   2. Service bypass: app.is_service_account=true → full access (workers,
--      result processing, login, OAuth, public billing, webhook triggers)
--
-- Usage:
--   1. Run this migration to create policies (RLS not enforced yet)
--   2. Test thoroughly in staging
--   3. Run add_rls_enforcement.sql to enable FORCE ROW LEVEL SECURITY
--
-- Note: Tables without organization_id (organizations, providers, site_content)
--       are excluded as they need different access patterns.

-- Helper function to get current org context (returns NULL if not set)
CREATE OR REPLACE FUNCTION current_org_id() RETURNS uuid AS $$
BEGIN
    RETURN NULLIF(current_setting('app.current_org_id', true), '')::uuid;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- Helper function to check if current session is a trusted service account.
-- Service accounts bypass org isolation for cross-org operations like:
-- worker job claims, result processing, login, OAuth callbacks, and
-- public billing endpoints.
CREATE OR REPLACE FUNCTION is_service_account() RETURNS boolean AS $$
BEGIN
    RETURN COALESCE(
        NULLIF(current_setting('app.is_service_account', true), '')::boolean,
        false
    );
EXCEPTION
    WHEN OTHERS THEN
        RETURN false;
END;
$$ LANGUAGE plpgsql STABLE;

-- ============================================================================
-- USERS TABLE
-- Users can only see/modify users in their own organization
-- ============================================================================
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS users_org_isolation ON users;
CREATE POLICY users_org_isolation ON users
    USING (organization_id = current_org_id())
    WITH CHECK (organization_id = current_org_id());

DROP POLICY IF EXISTS users_service_bypass ON users;
CREATE POLICY users_service_bypass ON users
    FOR ALL
    USING (is_service_account())
    WITH CHECK (is_service_account());

-- ============================================================================
-- WORKFLOWS TABLE
-- Workflows scoped to organization
-- ============================================================================
ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS workflows_org_isolation ON workflows;
CREATE POLICY workflows_org_isolation ON workflows
    USING (organization_id = current_org_id())
    WITH CHECK (organization_id = current_org_id());

DROP POLICY IF EXISTS workflows_service_bypass ON workflows;
CREATE POLICY workflows_service_bypass ON workflows
    FOR ALL
    USING (is_service_account())
    WITH CHECK (is_service_account());

-- ============================================================================
-- WORKFLOW_INSTANCES TABLE
-- Instances scoped to organization
-- ============================================================================
ALTER TABLE instances ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS instances_org_isolation ON instances;
CREATE POLICY instances_org_isolation ON instances
    USING (organization_id = current_org_id())
    WITH CHECK (organization_id = current_org_id());

DROP POLICY IF EXISTS instances_service_bypass ON instances;
CREATE POLICY instances_service_bypass ON instances
    FOR ALL
    USING (is_service_account())
    WITH CHECK (is_service_account());

-- ============================================================================
-- PROVIDER_CREDENTIALS TABLE
-- Credentials are highly sensitive - strict org isolation
-- ============================================================================
ALTER TABLE provider_credentials ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS provider_credentials_org_isolation ON provider_credentials;
CREATE POLICY provider_credentials_org_isolation ON provider_credentials
    USING (organization_id = current_org_id())
    WITH CHECK (organization_id = current_org_id());

DROP POLICY IF EXISTS provider_credentials_service_bypass ON provider_credentials;
CREATE POLICY provider_credentials_service_bypass ON provider_credentials
    FOR ALL
    USING (is_service_account())
    WITH CHECK (is_service_account());

-- ============================================================================
-- QUEUES TABLE
-- Queues scoped to organization
-- ============================================================================
ALTER TABLE queues ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS queues_org_isolation ON queues;
CREATE POLICY queues_org_isolation ON queues
    USING (organization_id = current_org_id())
    WITH CHECK (organization_id = current_org_id());

DROP POLICY IF EXISTS queues_service_bypass ON queues;
CREATE POLICY queues_service_bypass ON queues
    FOR ALL
    USING (is_service_account())
    WITH CHECK (is_service_account());

-- ============================================================================
-- QUEUED_JOBS TABLE
-- Jobs scoped to organization
-- ============================================================================
ALTER TABLE queued_jobs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS queued_jobs_org_isolation ON queued_jobs;
CREATE POLICY queued_jobs_org_isolation ON queued_jobs
    USING (organization_id = current_org_id())
    WITH CHECK (organization_id = current_org_id());

DROP POLICY IF EXISTS queued_jobs_service_bypass ON queued_jobs;
CREATE POLICY queued_jobs_service_bypass ON queued_jobs
    FOR ALL
    USING (is_service_account())
    WITH CHECK (is_service_account());

-- ============================================================================
-- AUDIT_EVENTS TABLE
-- Special visibility: super_admin sees all, org admins see their org only
-- This is an append-only audit log
-- ============================================================================
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

-- Select policy: super_admin sees all, org admins see their org's events
DROP POLICY IF EXISTS audit_events_visibility ON audit_events;
CREATE POLICY audit_events_visibility ON audit_events
    FOR SELECT
    USING (
        -- Super admin sees everything (org events + system events where org_id is null)
        current_setting('app.is_super_admin', true)::boolean = true
        OR (
            -- Org admin sees their org's events only (not system events)
            organization_id IS NOT NULL
            AND organization_id = current_org_id()
        )
    );

-- Insert policy: application can insert (audit events are append-only)
DROP POLICY IF EXISTS audit_events_insert ON audit_events;
CREATE POLICY audit_events_insert ON audit_events
    FOR INSERT
    WITH CHECK (true);

DROP POLICY IF EXISTS audit_events_service_bypass ON audit_events;
CREATE POLICY audit_events_service_bypass ON audit_events
    FOR ALL
    USING (is_service_account())
    WITH CHECK (is_service_account());

-- ============================================================================
-- NOTIFICATIONS TABLE
-- Notifications scoped to organization
-- ============================================================================
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS notifications_org_isolation ON notifications;
CREATE POLICY notifications_org_isolation ON notifications
    USING (organization_id = current_org_id())
    WITH CHECK (organization_id = current_org_id());

DROP POLICY IF EXISTS notifications_service_bypass ON notifications;
CREATE POLICY notifications_service_bypass ON notifications
    FOR ALL
    USING (is_service_account())
    WITH CHECK (is_service_account());

-- ============================================================================
-- NOTIFICATION_CHANNELS TABLE
-- Channels scoped to organization
-- ============================================================================
ALTER TABLE notification_channels ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS notification_channels_org_isolation ON notification_channels;
CREATE POLICY notification_channels_org_isolation ON notification_channels
    USING (organization_id = current_org_id())
    WITH CHECK (organization_id = current_org_id());

DROP POLICY IF EXISTS notification_channels_service_bypass ON notification_channels;
CREATE POLICY notification_channels_service_bypass ON notification_channels
    FOR ALL
    USING (is_service_account())
    WITH CHECK (is_service_account());

-- ============================================================================
-- ORG_FILES TABLE
-- Output resources scoped to organization
-- ============================================================================
ALTER TABLE org_files ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS org_files_org_isolation ON org_files;
CREATE POLICY org_files_org_isolation ON org_files
    USING (organization_id = current_org_id())
    WITH CHECK (organization_id = current_org_id());

DROP POLICY IF EXISTS org_files_service_bypass ON org_files;
CREATE POLICY org_files_service_bypass ON org_files
    FOR ALL
    USING (is_service_account())
    WITH CHECK (is_service_account());

-- ============================================================================
-- ORGANIZATION_SECRETS TABLE
-- Secrets are highly sensitive - strict org isolation
-- ============================================================================
ALTER TABLE organization_secrets ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS organization_secrets_org_isolation ON organization_secrets;
CREATE POLICY organization_secrets_org_isolation ON organization_secrets
    USING (organization_id = current_org_id())
    WITH CHECK (organization_id = current_org_id());

DROP POLICY IF EXISTS organization_secrets_service_bypass ON organization_secrets;
CREATE POLICY organization_secrets_service_bypass ON organization_secrets
    FOR ALL
    USING (is_service_account())
    WITH CHECK (is_service_account());

-- ============================================================================
-- Summary of RLS status
-- ============================================================================
DO $$
DECLARE
    tbl RECORD;
    policy_count INT;
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '=== RLS Policy Summary ===';

    FOR tbl IN
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename
    LOOP
        SELECT COUNT(*) INTO policy_count
        FROM pg_policies
        WHERE tablename = tbl.tablename AND schemaname = 'public';

        IF policy_count > 0 THEN
            RAISE NOTICE 'Table: % - % policies', tbl.tablename, policy_count;
        END IF;
    END LOOP;

    RAISE NOTICE '';
    RAISE NOTICE 'RLS policies created but NOT ENFORCED yet.';
    RAISE NOTICE 'Each table has: org_isolation policy + service_bypass policy.';
    RAISE NOTICE 'Run add_rls_enforcement.sql to enable FORCE ROW LEVEL SECURITY.';
    RAISE NOTICE '';
END $$;
