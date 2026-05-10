// ui/app/providers/list/page.tsx

"use client";

import { DashboardLayout } from "@/widgets/layout";
import ProvidersList from '../components/ProvidersList';
import { ProvidersMarketplaceTab } from '../components/ProvidersMarketplaceTab';
import Link from 'next/link';
import { useUser } from '@/entities/user';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect } from 'react';
import { Upload } from 'lucide-react';

type ActiveTab = 'organization' | 'custom' | 'marketplace';

export default function ProvidersListPage() {
  return (
    <Suspense>
      <ProvidersListContent />
    </Suspense>
  );
}

function ProvidersListContent() {
  const { user, status: authStatus } = useUser();
  const router = useRouter();
  const searchParams = useSearchParams();

  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin';
  const isSuperAdmin = user?.role === 'super_admin';

  // Tab state derived from URL (single source of truth)
  const defaultTab: ActiveTab = isSuperAdmin ? 'marketplace' : 'organization';
  const tabParam = searchParams.get('tab') as ActiveTab | null;
  const allowedTabs: ActiveTab[] = isSuperAdmin
    ? ['custom', 'marketplace']
    : isAdmin
      ? ['organization', 'marketplace']
      : ['organization'];
  const requested: ActiveTab | null = tabParam
    ? tabParam
    : authStatus === 'authenticated'
      ? defaultTab
      : null;
  const activeTab: ActiveTab | null = requested && allowedTabs.includes(requested) ? requested : (authStatus === 'authenticated' ? defaultTab : null);

  // Sync URL when the resolved tab differs from what was requested
  useEffect(() => {
    if (authStatus !== 'authenticated') return;
    if (tabParam && activeTab && activeTab !== tabParam) {
      router.replace(`/providers/list?tab=${activeTab}`, { scroll: false });
    }
  }, [tabParam, activeTab, authStatus, router]);

  const setActiveTab = (tab: ActiveTab) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set('tab', tab);
    router.replace(`/providers/list?${params.toString()}`, { scroll: false });
  };

  return (
    <DashboardLayout>
      <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-9xl mx-auto">
        <div className="flex flex-wrap justify-between items-center gap-4 mb-8">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-primary">
              Providers
            </h1>
            <p className="section-subtitle mt-1">
              {isSuperAdmin
                ? 'Manage custom providers available for organizations to install'
                : 'Manage and configure service providers for your workflows'}
            </p>
          </div>
          {user?.role === 'super_admin' && (activeTab === 'organization' || activeTab === 'custom') && (
            <div className="grid grid-flow-col sm:auto-cols-max justify-start sm:justify-end gap-2">
              <Link
                href="/providers/create"
                className="btn-primary inline-flex items-center justify-center gap-2"
              >
                <Upload size={16} />
                Upload Provider
              </Link>
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="border-b border-primary mb-6">
          <nav className="flex space-x-4" aria-label="Provider filters">
            <button
              type="button"
              onClick={() => setActiveTab(isSuperAdmin ? 'custom' : 'organization')}
              className={`tab ${(activeTab === 'organization' || activeTab === 'custom') ? 'tab-active' : 'tab-inactive'}`}
            >
              {isSuperAdmin ? 'Custom' : 'Organization'}
            </button>
            {isAdmin && (
              <button
                type="button"
                onClick={() => setActiveTab('marketplace')}
                className={`tab ${activeTab === 'marketplace' ? 'tab-active' : 'tab-inactive'}`}
              >
                Marketplace
              </button>
            )}
          </nav>
        </div>

        {/* Organization tab */}
        {(activeTab === 'organization' || activeTab === 'custom') && (
          <ProvidersList providerTypeFilter={isSuperAdmin ? 'custom' : undefined} />
        )}

        {/* Marketplace tab */}
        {activeTab === 'marketplace' && isAdmin && (
          <ProvidersMarketplaceTab isSuperAdmin={isSuperAdmin} />
        )}
      </div>
    </DashboardLayout>
  );
}
