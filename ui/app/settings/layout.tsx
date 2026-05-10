// ui/app/settings/layout.tsx

'use client';

import { DashboardLayout } from "@/widgets/layout";
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useUser } from '@/entities/user';

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { user } = useUser();

  const baseTabs = [
    { id: 'profile', label: 'Profile', path: '/settings/profile' },
    { id: 'account', label: 'Account', path: '/settings/account' },
  ];

  // Add Site Content tab for super_admin users
  const tabs = user?.role === 'super_admin'
    ? [...baseTabs, { id: 'site', label: 'Site Content', path: '/settings/site' }]
    : baseTabs;

  return (
    <DashboardLayout>
      <div className="px-4 py-6 sm:px-6 lg:px-8">
        <div className="sm:flex sm:items-center mb-8">
          <div className="sm:flex-auto">
            <h1 className="text-2xl font-semibold text-primary">
              Settings
            </h1>
            <p className="mt-2 text-sm text-secondary">
              Manage your account settings and preferences.
            </p>
          </div>
        </div>

        {/* Tabs */}
        <div className="border-b border-primary mb-8">
          <div className="max-w-5xl mx-auto px-4">
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
        </div>

        {/* Tab content */}
        <div className="mt-6">{children}</div>
      </div>
    </DashboardLayout>
  );
}
