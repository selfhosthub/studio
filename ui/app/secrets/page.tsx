// ui/app/secrets/page.tsx

'use client';

import { DashboardLayout } from '@/widgets/layout';
import Link from 'next/link';
import { Suspense, useEffect, useState, useMemo } from 'react';
import { useUser } from '@/entities/user';
import { useRouter, useSearchParams } from 'next/navigation';
import { Key, Lock, Plus } from 'lucide-react';
import { getProviders, getOrganizationCredentials, getOrganizationSecrets } from '@/shared/api';
import type { Provider as ApiProvider, ProviderCredential, OrganizationSecret as ApiOrgSecret } from '@/shared/api/providers';
import {
  LinkedText,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableCell,
  TableHeaderCell,
  TableContainer,
  StatusBadge,
  ActionButton,
  LoadingState,
  ErrorState,
  EmptyState,
  SearchInput,
  Pagination,
} from '@/shared/ui';
import { PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';
import { PAGINATION } from '@/shared/lib/constants';
type TabType = 'organization' | 'providers';

// Format date as "MM/DD/YYYY HH:MM:SS UTC" (24-hour, no comma, UTC timezone)
const formatDateTime = (dateStr: string) => {
  const d = new Date(dateStr);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${pad(d.getUTCMonth() + 1)}/${pad(d.getUTCDate())}/${d.getUTCFullYear()} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`;
};

type Provider = ApiProvider;
type Credential = ProviderCredential;
type OrganizationSecret = ApiOrgSecret;

export default function SecretsPage() {
  return (
    <Suspense>
      <SecretsPageContent />
    </Suspense>
  );
}

function SecretsPageContent() {
  const { user, status: authStatus } = useUser();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [credentials, setCredentials] = useState<Record<string, Credential[]>>({});
  const [orgSecrets, setOrgSecrets] = useState<OrganizationSecret[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Tab state - default to providers, respect ?tab= param
  const tabParam = searchParams.get('tab') as TabType | null;
  const [activeTab, setActiveTabState] = useState<TabType>(
    tabParam === 'organization' ? 'organization' : 'providers'
  );

  // Sync tab to URL
  const setActiveTab = (tab: TabType) => {
    setActiveTabState(tab);
    const params = new URLSearchParams(searchParams.toString());
    params.set('tab', tab);
    router.replace(`/secrets?${params.toString()}`, { scroll: false });
  };

  // Organization secrets search and pagination
  const [orgSearchTerm, setOrgSearchTerm] = useState('');
  const [orgCurrentPage, setOrgCurrentPage] = useState(1);
  const [orgPageSize, setOrgPageSize] = useState(PAGINATION.DEFAULT_PAGE_SIZE);

  // Provider credentials search and pagination
  const [providerSearchTerm, setProviderSearchTerm] = useState('');
  const [providerCurrentPage, setProviderCurrentPage] = useState(1);
  const [providerPageSize, setProviderPageSize] = useState(PAGINATION.DEFAULT_PAGE_SIZE);

  useEffect(() => {
    if (authStatus === 'loading') return;
    if (authStatus === 'unauthenticated') {
      router.push('/login');
      return;
    }

    const fetchData = async () => {
      try {
        setLoading(true);

        // Super admin only sees organization secrets, not provider credentials
        if (user?.role === 'super_admin') {
          const orgSecretsData = await getOrganizationSecrets().catch(err => {
            console.error('Failed to fetch organization secrets:', err);
            return [];
          });
          setOrgSecrets(orgSecretsData);
          setProviders([]);
          setCredentials({});
        } else {
          // Regular users see both organization secrets and provider credentials
          const [orgSecretsData, providersData, allCredentialsData] = await Promise.all([
            getOrganizationSecrets().catch(err => {
              console.error('Failed to fetch organization secrets:', err);
              return [];
            }),
            getProviders(),
            getOrganizationCredentials().catch(err => {
              console.error('Failed to fetch provider credentials:', err);
              return [];
            })
          ]);

          setOrgSecrets(orgSecretsData);
          setProviders(providersData);

          // Group credentials by provider_id
          const credentialsMap: Record<string, Credential[]> = {};

          // Initialize empty arrays for all providers
          for (const provider of providersData) {
            credentialsMap[provider.id] = [];
          }

          // Populate credentials map from the single API call
          for (const cred of allCredentialsData) {
            if (cred.provider_id && credentialsMap[cred.provider_id]) {
              credentialsMap[cred.provider_id].push(cred);
            }
          }

          setCredentials(credentialsMap);
        }
      } catch (err: unknown) {
        console.error('Failed to load secrets data:', err);
        setError(err instanceof Error ? err.message : 'Failed to load secrets data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [authStatus, router, user?.role]);

  // Filter organization secrets based on search
  const filteredOrgSecrets = useMemo(() => {
    return orgSecrets.filter(
      (secret) =>
        secret.name?.toLowerCase().includes(orgSearchTerm.toLowerCase()) ||
        secret.description?.toLowerCase().includes(orgSearchTerm.toLowerCase()) ||
        secret.secret_type?.toLowerCase().includes(orgSearchTerm.toLowerCase())
    );
  }, [orgSecrets, orgSearchTerm]);

  // Reset org page when search changes
  useEffect(() => {
    setOrgCurrentPage(1);
  }, [orgSearchTerm]);

  // Org secrets pagination calculations
  const orgTotalCount = filteredOrgSecrets.length;
  const orgTotalPages = Math.ceil(orgTotalCount / orgPageSize) || 1;
  const paginatedOrgSecrets = filteredOrgSecrets.slice(
    (orgCurrentPage - 1) * orgPageSize,
    orgCurrentPage * orgPageSize
  );

  // Filter providers based on search (for provider credentials tab)
  const filteredProviders = useMemo(() => {
    return providers.filter(
      (provider) =>
        provider.name?.toLowerCase().includes(providerSearchTerm.toLowerCase()) ||
        provider.description?.toLowerCase().includes(providerSearchTerm.toLowerCase())
    );
  }, [providers, providerSearchTerm]);

  // Reset provider page when search changes
  useEffect(() => {
    setProviderCurrentPage(1);
  }, [providerSearchTerm]);

  // Provider pagination calculations
  const providerTotalCount = filteredProviders.length;
  const providerTotalPages = Math.ceil(providerTotalCount / providerPageSize) || 1;
  const paginatedProviders = filteredProviders.slice(
    (providerCurrentPage - 1) * providerPageSize,
    providerCurrentPage * providerPageSize
  );

  if (loading || authStatus === 'loading') {
    return (
      <DashboardLayout>
        <LoadingState message="Loading secrets..." />
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout>
        <ErrorState
          title="Error Loading Secrets"
          message={error}
          onRetry={() => window.location.reload()}
          retryLabel="Try Again"
        />
      </DashboardLayout>
    );
  }

  // Show tabs only for non-super_admin users
  const showTabs = user?.role !== 'super_admin';

  return (
    <DashboardLayout>
      <div className="px-4 py-6 sm:px-6 lg:px-8">
        <div className="sm:flex sm:items-center mb-8">
          <div className="sm:flex-auto">
            <h1 className="text-2xl font-semibold text-primary">
              {user?.role === 'super_admin' ? 'System Secrets' : 'Secrets & Credentials'}
            </h1>
            <p className="mt-2 text-sm text-secondary">
              {user?.role === 'super_admin'
                ? 'Manage system-level secrets like the Entitlement Token.'
                : 'Manage your organization secrets, provider credentials, and API keys securely.'}
            </p>
          </div>
        </div>

        {/* Tabs - Only for non-super_admin */}
        {showTabs && (
          <div className="border-b border-primary mb-6">
            <nav className="-mb-px flex space-x-8" aria-label="Tabs">
              <button
                onClick={() => setActiveTab('providers')}
                className={`tab whitespace-nowrap py-4 ${
                  activeTab === 'providers' ? 'tab-active' : 'tab-inactive'
                }`}
              >
                Provider Credentials ({providerTotalCount})
              </button>
              <button
                onClick={() => setActiveTab('organization')}
                className={`tab whitespace-nowrap py-4 ${
                  activeTab === 'organization' ? 'tab-active' : 'tab-inactive'
                }`}
              >
                Organization Secrets ({orgTotalCount})
              </button>
            </nav>
          </div>
        )}

        {/* Organization Secrets Tab Content */}
        {(activeTab === 'organization' || !showTabs) && (
          <div>
            {/* Search and Pagination Controls */}
            <div className="flex items-center justify-between gap-4 mb-4">
              <SearchInput
                value={orgSearchTerm}
                onChange={setOrgSearchTerm}
                placeholder="Search secrets..."
              />
              <div className="flex items-center gap-4">
                <Link
                  href="/secrets/new"
                  className="btn-primary inline-flex items-center"
                >
                  <Plus className="mr-2 h-4 w-4" />
                  New Secret
                </Link>
                <Pagination
                  currentPage={orgCurrentPage}
                  totalPages={orgTotalPages}
                  totalCount={orgTotalCount}
                  pageSize={orgPageSize}
                  onPageChange={setOrgCurrentPage}
                  onPageSizeChange={(size) => {
                    setOrgPageSize(size);
                    setOrgCurrentPage(1);
                  }}
                  pageSizeOptions={PAGE_SIZE_OPTIONS}
                  position="top"
                />
              </div>
            </div>

            {paginatedOrgSecrets.length === 0 ? (
              <EmptyState
                icon={<Key className="h-12 w-12" />}
                title="No secrets found"
                description={orgSearchTerm ? 'Try adjusting your search term.' : 'Get started by creating an organization secret.'}
              />
            ) : (
              <>
                <TableContainer>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHeaderCell>Name</TableHeaderCell>
                        <TableHeaderCell align="center">Type</TableHeaderCell>
                        <TableHeaderCell align="center">Status</TableHeaderCell>
                        <TableHeaderCell align="center">Created</TableHeaderCell>
                        <TableHeaderCell align="center">Expires</TableHeaderCell>
                        <TableHeaderCell align="center">Actions</TableHeaderCell>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paginatedOrgSecrets.map((secret) => (
                        <TableRow key={secret.id}>
                          <TableCell>
                            <div className="flex items-start">
                              <Key className="h-5 w-5 text-info mr-3 mt-0.5 flex-shrink-0" />
                              <div>
                                <div className="flex items-center gap-2">
                                  <span className="text-sm font-medium">
                                    {secret.name}
                                  </span>
                                  {secret.is_protected && (
                                    <span title="Protected - cannot be deleted">
                                      <Lock className="h-3.5 w-3.5 text-warning" />
                                    </span>
                                  )}
                                </div>
                                {secret.description && (
                                  <div className="text-xs text-muted mt-0.5">
                                    <LinkedText text={secret.description} />
                                  </div>
                                )}
                              </div>
                            </div>
                          </TableCell>
                          <TableCell align="center">
                            <StatusBadge status={secret.secret_type} variant="default" />
                          </TableCell>
                          <TableCell align="center">
                            <StatusBadge
                              status={secret.is_active ? 'Active' : 'Inactive'}
                              variant={secret.is_active ? 'success' : 'error'}
                            />
                          </TableCell>
                          <TableCell align="center">
                            {formatDateTime(secret.created_at || '')}
                          </TableCell>
                          <TableCell align="center">
                            {secret.expires_at ? formatDateTime(secret.expires_at) : '-'}
                          </TableCell>
                          <TableCell align="center">
                            <ActionButton
                              variant="change"
                              onClick={() => router.push(`/secrets/${secret.id}/edit`)}
                            >
                              Manage
                            </ActionButton>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>

                {/* Bottom Pagination */}
                <Pagination
                  currentPage={orgCurrentPage}
                  totalPages={orgTotalPages}
                  totalCount={orgTotalCount}
                  pageSize={orgPageSize}
                  onPageChange={setOrgCurrentPage}
                  itemLabel="secret"
                  position="bottom"
                />
              </>
            )}
          </div>
        )}

        {/* Provider Credentials Tab Content */}
        {activeTab === 'providers' && showTabs && (
          <div>
            {/* Search and Pagination Controls */}
            <div className="flex items-center justify-between gap-4 mb-4">
              <SearchInput
                value={providerSearchTerm}
                onChange={setProviderSearchTerm}
                placeholder="Search providers..."
              />
              <Pagination
                currentPage={providerCurrentPage}
                totalPages={providerTotalPages}
                totalCount={providerTotalCount}
                pageSize={providerPageSize}
                onPageChange={setProviderCurrentPage}
                onPageSizeChange={(size) => {
                  setProviderPageSize(size);
                  setProviderCurrentPage(1);
                }}
                pageSizeOptions={PAGE_SIZE_OPTIONS}
                position="top"
              />
            </div>

            {paginatedProviders.length === 0 ? (
              <EmptyState
                icon={<Key className="h-12 w-12" />}
                title="No providers found"
                description={providerSearchTerm ? 'Try adjusting your search term.' : 'Get started by adding a provider.'}
                action={
                  !providerSearchTerm ? (
                    <Link
                      href="/providers"
                      className="btn-primary inline-flex items-center"
                    >
                      <Key className="mr-2 h-4 w-4" />
                      Go to Providers
                    </Link>
                  ) : undefined
                }
              />
            ) : (
              <>
                <TableContainer>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHeaderCell>Provider</TableHeaderCell>
                        <TableHeaderCell>Credential Name</TableHeaderCell>
                        <TableHeaderCell align="center">Type</TableHeaderCell>
                        <TableHeaderCell align="center">Created</TableHeaderCell>
                        <TableHeaderCell align="center">Expires</TableHeaderCell>
                        <TableHeaderCell align="center">Actions</TableHeaderCell>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paginatedProviders.map((provider) => {
                        const providerCreds = credentials[provider.id] || [];

                        if (providerCreds.length === 0) {
                          return (
                            <TableRow key={provider.id}>
                              <TableCell>
                                <div className="text-sm font-medium">
                                  {provider.name}
                                </div>
                                <div className="text-muted text-xs">
                                  {provider.description || `${provider.provider_type} provider`}
                                </div>
                              </TableCell>
                              <TableCell colSpan={4} className="text-muted italic">
                                No credentials configured
                              </TableCell>
                              <TableCell align="center">
                                <ActionButton
                                  variant="change"
                                  onClick={() => router.push(`/providers/${provider.id}/credentials`)}
                                >
                                  Manage
                                </ActionButton>
                              </TableCell>
                            </TableRow>
                          );
                        }

                        return providerCreds.map((cred, index) => (
                          <tr key={cred.id} className="table-row">
                            {index === 0 && (
                              <td className="table-cell" rowSpan={providerCreds.length}>
                                <div className="text-sm font-medium">
                                  {provider.name}
                                </div>
                                <div className="text-muted text-xs">
                                  {provider.description || `${provider.provider_type} provider`}
                                </div>
                              </td>
                            )}
                            <td className="table-cell">
                              <div className="flex items-center">
                                <Key className="h-4 w-4 text-muted mr-2" />
                                <div className="text-sm font-medium">
                                  {cred.name}
                                </div>
                              </div>
                            </td>
                            <td className="table-cell text-center">
                              <StatusBadge status={cred.credential_type} variant="default" />
                            </td>
                            <td className="table-cell text-center text-sm text-muted">
                              {formatDateTime(cred.created_at || '')}
                            </td>
                            <td className="table-cell text-center text-sm text-muted">
                              {cred.expires_at ? formatDateTime(cred.expires_at) : '-'}
                            </td>
                            {index === 0 && (
                              <td className="table-cell text-center" rowSpan={providerCreds.length}>
                                <ActionButton
                                  variant="change"
                                  onClick={() => router.push(`/providers/${provider.id}/credentials`)}
                                >
                                  Manage
                                </ActionButton>
                              </td>
                            )}
                          </tr>
                        ));
                      })}
                    </TableBody>
                  </Table>
                </TableContainer>

                {/* Bottom Pagination */}
                <Pagination
                  currentPage={providerCurrentPage}
                  totalPages={providerTotalPages}
                  totalCount={providerTotalCount}
                  pageSize={providerPageSize}
                  onPageChange={setProviderCurrentPage}
                  itemLabel="provider"
                  position="bottom"
                />
              </>
            )}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
