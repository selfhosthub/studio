// ui/app/organization/manage/layout.tsx

'use client';

import { DashboardLayout } from "@/widgets/layout";
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useRoleAccess } from '@/features/roles';
import { useUser } from '@/entities/user';

export default function OrganizationManageLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { user } = useUser();
  const { hasAccess, isLoading: authLoading } = useRoleAccess(['admin', 'super_admin']);

  const isSuperAdmin = user?.role === 'super_admin';

  const tabs = [
    { id: 'details', label: 'Details', path: '/organization/manage/details' },
    { id: 'users', label: 'Users', path: '/organization/manage/users' },
    { id: 'settings', label: 'Settings', path: '/organization/manage/settings' },
    // Only show branding tab for super-admins (branding is system-level, not org-level)
    ...(isSuperAdmin ? [{ id: 'branding', label: 'Branding', path: '/organization/manage/branding' }] : []),
  ];

  // Show loading state while checking access
  if (authLoading) {
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
        <div className="sm:flex sm:items-center mb-8">
          <div className="sm:flex-auto">
            <h1 className="text-2xl font-semibold text-primary">
              Organization Management
            </h1>
            <p className="mt-2 text-sm text-secondary">
              Manage your organization settings, users, and permissions.
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
