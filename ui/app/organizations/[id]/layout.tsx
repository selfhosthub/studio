// ui/app/organizations/[id]/layout.tsx

'use client';

import { useMemo, useState, useEffect } from 'react';
import { DashboardLayout } from "@/widgets/layout";
import Link from 'next/link';
import { usePathname, useParams } from 'next/navigation';
import { useUser } from '@/entities/user';
import { getOrganization } from '@/shared/api';

export default function OrganizationLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const params = useParams();
  const orgId = params.id as string;
  const { user, status } = useUser();
  // Check admin/super_admin status directly without useRoleAccess hook (which auto-redirects)
  const isAdminOrSuper = user?.role === 'admin' || user?.role === 'super_admin';
  const authLoading = status === 'loading';
  const [orgName, setOrgName] = useState<string | null>(null);
  const [orgLoading, setOrgLoading] = useState(true);

  // Allow access if user is admin/super_admin OR if user is viewing their own org
  const isViewingOwnOrg = user?.org_id === orgId;
  const hasAccess = isAdminOrSuper || isViewingOwnOrg;

  // Check if user can edit (only admins of their own org)
  const canEdit = (user?.role === 'admin' || user?.role === 'super_admin') && isViewingOwnOrg;

  // Fetch org to check if it's the system org and get org name
  useEffect(() => {
    if (!orgId || !user) return;

    getOrganization(orgId)
      .then((org) => {
        setOrgName(org?.name || null);
      })
      .catch(() => {
        setOrgName(null);
      })
      .finally(() => {
        setOrgLoading(false);
      });
  }, [orgId, user]);

  const isSuperAdmin = user?.role === 'super_admin';

  // Check if super-admin is viewing a different org
  const isViewingOtherOrg = isSuperAdmin && user?.org_id !== orgId;

  const tabs = useMemo(() => {
    const baseTabs = [
      { id: 'details', label: 'Details', path: `/organizations/${orgId}` },
    ];

    // Users tab only for admins
    if (isAdminOrSuper) {
      baseTabs.push({ id: 'users', label: 'Users', path: `/organizations/${orgId}/users` });
    }

    // Branding is super-admin only
    if (isSuperAdmin) {
      baseTabs.push({ id: 'branding', label: 'Branding', path: `/organizations/${orgId}/branding` });
    }

    return baseTabs;
  }, [orgId, isAdminOrSuper, isSuperAdmin]);

  // Show loading state while checking access and org data
  if (authLoading || orgLoading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-muted">Loading...</div>
        </div>
      </DashboardLayout>
    );
  }

  // Show access denied if user doesn't have permission
  if (!hasAccess) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <h2 className="text-xl font-semibold text-danger mb-2">Access Denied</h2>
            <p className="text-secondary">
              You do not have permission to view this page. Only administrators can access organization management.
            </p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="px-4 py-6 sm:px-6 lg:px-8">
        {/* Super-admin banner when viewing another org */}
        {isViewingOtherOrg && orgName && (
          <div className="mb-6 bg-warning-subtle border border-warning rounded-lg p-4">
            <div className="flex items-center">
              <svg className="h-5 w-5 text-warning mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div>
                <p className="text-lg text-warning">
                  Viewing <span className="font-bold">{orgName}</span>&apos;s organization settings
                </p>
              </div>
            </div>
          </div>
        )}

        <div className="sm:flex sm:items-center mb-8">
          <div className="sm:flex-auto">
            <h1 className="text-2xl font-semibold text-primary">
              Organization Management
            </h1>
            <p className="mt-2 text-sm text-secondary">
              Manage organization settings, users, and permissions.
            </p>
          </div>
        </div>

        {/* Tabs */}
        <div className="border-b border-primary">
          <nav
            className="-mb-px flex space-x-4 sm:space-x-8 overflow-x-auto scrollbar-hide"
            aria-label="Tabs"
          >
            {tabs.map((tab) => (
              <Link
                key={tab.id}
                href={tab.path}
                className={`${
                  pathname === tab.path
                    ? 'border-info text-info'
                    : 'border-transparent text-secondary hover:text-secondary hover:border-primary'
                } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex-shrink-0`}
              >
                {tab.label}
              </Link>
            ))}
          </nav>
        </div>

        {/* Tab content */}
        <div className="mt-6">{children}</div>
      </div>
    </DashboardLayout>
  );
}
