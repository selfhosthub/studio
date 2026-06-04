-- RLS Enforcement Migration
--
-- This migration enables FORCE ROW LEVEL SECURITY on all tables.
-- Run this AFTER add_rls_policies.sql and thorough testing in staging.
--
-- FORCE means even table owners (superusers) are subject to RLS policies.
-- This provides defense-in-depth against application bugs.
--
-- WARNING: After running this, all queries MUST have app.current_org_id set
-- or app.is_service_account=true, or they will return no rows for
-- RLS-protected tables.

-- ============================================================================
-- Enable FORCE on all RLS-enabled tables
-- ============================================================================

ALTER TABLE users FORCE ROW LEVEL SECURITY;
-- templates: removed - table no longer exists in the schema
-- resources: removed - table no longer exists in the schema
ALTER TABLE workflows FORCE ROW LEVEL SECURITY;
ALTER TABLE instances FORCE ROW LEVEL SECURITY;
ALTER TABLE provider_credentials FORCE ROW LEVEL SECURITY;
ALTER TABLE queues FORCE ROW LEVEL SECURITY;
ALTER TABLE queued_jobs FORCE ROW LEVEL SECURITY;
-- webhooks: removed - webhook data lives as columns on the workflows table,
-- which is already RLS-protected. No separate webhooks table exists.
ALTER TABLE notifications FORCE ROW LEVEL SECURITY;
ALTER TABLE notification_channels FORCE ROW LEVEL SECURITY;
ALTER TABLE org_files FORCE ROW LEVEL SECURITY;
ALTER TABLE organization_secrets FORCE ROW LEVEL SECURITY;

-- ============================================================================
-- Verification
-- ============================================================================
DO $$
DECLARE
    tbl RECORD;
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '=== RLS Enforcement Status ===';

    FOR tbl IN
        SELECT
            c.relname as tablename,
            c.relrowsecurity as rls_enabled,
            c.relforcerowsecurity as rls_forced
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'r'
          AND c.relrowsecurity = true
        ORDER BY c.relname
    LOOP
        IF tbl.rls_forced THEN
            RAISE NOTICE 'Table: % - RLS ENFORCED', tbl.tablename;
        ELSE
            RAISE NOTICE 'Table: % - RLS enabled but NOT forced (warning)', tbl.tablename;
        END IF;
    END LOOP;

    RAISE NOTICE '';
    RAISE NOTICE 'RLS enforcement complete.';
    RAISE NOTICE 'All queries must now set app.current_org_id or app.is_service_account for protected tables.';
    RAISE NOTICE '';
END $$;
