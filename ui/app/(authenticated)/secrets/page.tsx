// ui/app/(authenticated)/secrets/page.tsx

'use client';

import Link from 'next/link';
import { Suspense, useEffect, useState, useMemo } from 'react';
import { useUser } from '@/entities/user';
import { useRouter, useSearchParams } from 'next/navigation';
import { Key, Lock, Plus } from 'lucide-react';
import { getProviders, getOrganizationCredentials, getOrganizationSecrets } from '@/shared/api';
import type { Provider as ApiProvider, ProviderCredential, OrganizationSecret as ApiOrgSecret } from '@/shared/api/providers';
import {
  LinkedText,
  StatusBadge,
  ActionButton,
  LoadingState,
  ErrorState,
  EmptyState,
  SearchInput,
  ResourceTable,
  type ResourceColumnConfig,
} from '@/shared/ui';
import { withReturnTo } from '@/shared/hooks/useReturnTo';
import { formatDate } from '@/shared/lib/dateFormatter';
import { secretTypeLabel } from '@/shared/lib/secret-labels';
type TabType = 'organization' | 'providers';

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

  // Where editors should return to: this list, including the active tab.
  const currentUrl = `/secrets?tab=${activeTab}`;

  // Organization secrets and provider credentials search
  const [orgSearchTerm, setOrgSearchTerm] = useState('');
  const [providerSearchTerm, setProviderSearchTerm] = useState('');

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
        secret.secret_type?.toLowerCase().includes(orgSearchTerm.toLowerCase()) ||
        secretTypeLabel(secret.secret_type).toLowerCase().includes(orgSearchTerm.toLowerCase())
    );
  }, [orgSecrets, orgSearchTerm]);

  const orgTotalCount = filteredOrgSecrets.length;

  // Filter providers by provider name, description or any credential name
  const filteredProviders = useMemo(() => {
    const term = providerSearchTerm.toLowerCase();
    return providers.filter(
      (provider) =>
        provider.name?.toLowerCase().includes(term) ||
        provider.description?.toLowerCase().includes(term) ||
        (credentials[provider.id] || []).some((cred) => cred.name?.toLowerCase().includes(term))
    );
  }, [providers, credentials, providerSearchTerm]);

  const credsOf = (provider: Provider) => credentials[provider.id] || [];

  const providerTotalCount = filteredProviders.reduce((n, p) => n + credsOf(p).length, 0);

  if (loading || authStatus === 'loading') {
    return (
      <>
        <LoadingState message="Loading secrets..." />
      </>
    );
  }

  if (error) {
    return (
      <>
        <ErrorState
          title="Error Loading Secrets"
          message={error}
          onRetry={() => window.location.reload()}
          retryLabel="Try Again"
        />
      </>
    );
  }

  // Show tabs only for non-super_admin users
  const showTabs = user?.role !== 'super_admin';

  // Managing org secrets and provider credentials is admin-only (matches the
  // backend: list/get/create/update/delete secrets all require admin). Regular
  // users may still browse provider credentials but get no org-secrets tab and
  // no Manage controls.
  const canManageSecrets = user?.role === 'admin' || user?.role === 'super_admin';
  // A non-admin who lands on ?tab=organization is bounced to providers.
  const effectiveTab = !canManageSecrets && activeTab === 'organization' ? 'providers' : activeTab;

  const manageProviderCell = (provider: Provider) => (canManageSecrets ? (
    <ActionButton
      variant="change"
      onClick={() => router.push(withReturnTo(`/providers/${provider.id}/credentials`, currentUrl))}
    >
      Credentials
    </ActionButton>
  ) : (
    <span className="text-muted">-</span>
  ));

  // Sort keys over every credential a provider row shows
  const firstText = (values: (string | undefined)[]) =>
    values.filter((v): v is string => !!v).sort((a, b) => a.localeCompare(b))[0];
  const dateTimes = (values: (string | null | undefined)[]) =>
    values.filter((v): v is string => !!v).map((v) => new Date(v).getTime());
  const newestCreated = (provider: Provider) => {
    const times = dateTimes(credsOf(provider).map((c) => c.created_at));
    return times.length ? new Date(Math.max(...times)) : null;
  };
  const soonestExpiry = (provider: Provider) => {
    const times = dateTimes(credsOf(provider).map((c) => c.expires_at));
    return times.length ? new Date(Math.min(...times)) : null;
  };

  const isExpired = (expiresAt: string | null | undefined) => !!expiresAt && new Date(expiresAt) < new Date();
  const expiresCell = (expiresAt: string | null | undefined) => (
    <>
      <span>{expiresAt ? formatDate(expiresAt) : '-'}</span>
      {isExpired(expiresAt) && <span className="badge-error ml-2">expired</span>}
    </>
  );

  const orgColumns: ResourceColumnConfig<OrganizationSecret>[] = [
    {
      key: 'name',
      header: 'Name',
      sortValue: (secret) => secret.name,
      render: (secret) => (
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
      ),
    },
    {
      key: 'type',
      header: 'Type',
      align: 'center',
      sortValue: (secret) => secretTypeLabel(secret.secret_type),
      render: (secret) => <StatusBadge status={secretTypeLabel(secret.secret_type)} variant="default" />,
    },
    {
      key: 'status',
      header: 'Status',
      align: 'center',
      sortValue: (secret) => secret.is_active,
      render: (secret) => (
        <StatusBadge
          status={secret.is_active ? 'active' : 'inactive'}
          variant={secret.is_active ? 'success' : 'error'}
        />
      ),
    },
    {
      key: 'created',
      header: 'Created',
      align: 'center',
      sortValue: (secret) => (secret.created_at ? new Date(secret.created_at) : null),
      render: (secret) => formatDate(secret.created_at || ''),
    },
    {
      key: 'expires',
      header: 'Expires',
      align: 'center',
      sortValue: (secret) => (secret.expires_at ? new Date(secret.expires_at) : null),
      render: (secret) => expiresCell(secret.expires_at),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'center',
      render: (secret) => (
        <ActionButton
          variant="change"
          onClick={() => router.push(withReturnTo(`/secrets/${secret.id}/edit`, currentUrl))}
        >
          Edit
        </ActionButton>
      ),
    },
  ];

  // One row per provider; its credentials stack inside the credential cells.
  const providerColumns: ResourceColumnConfig<Provider>[] = [
    {
      key: 'provider',
      header: 'Provider',
      sortValue: (provider) => provider.name,
      render: (provider) => (
        <>
          <div className="text-sm font-medium">
            {provider.name}
          </div>
          <div className="text-muted text-xs">
            {provider.description || `${provider.provider_type} provider`}
          </div>
        </>
      ),
    },
    {
      key: 'credential',
      header: 'Credential Name',
      sortValue: (provider) => firstText(credsOf(provider).map((c) => c.name)),
      render: (provider) => {
        const creds = credsOf(provider);
        if (creds.length === 0) {
          return <span className="text-muted italic">No credentials configured</span>;
        }
        return (
          <div className="space-y-2">
            {creds.map((cred) => (
              <div key={cred.id} className="flex items-center">
                <Key className="h-4 w-4 text-muted mr-2" />
                <div className="text-sm font-medium">
                  {cred.name}
                </div>
              </div>
            ))}
          </div>
        );
      },
    },
    {
      key: 'type',
      header: 'Type',
      align: 'center',
      sortValue: (provider) => firstText(credsOf(provider).map((c) => secretTypeLabel(c.credential_type))),
      render: (provider) => (
        <div className="space-y-2">
          {credsOf(provider).map((cred) => (
            <div key={cred.id}>
              <StatusBadge status={secretTypeLabel(cred.credential_type)} variant="default" />
            </div>
          ))}
        </div>
      ),
    },
    {
      key: 'created',
      header: 'Created',
      align: 'center',
      sortValue: newestCreated,
      cellClassName: 'text-sm text-muted',
      render: (provider) => (
        <div className="space-y-2">
          {credsOf(provider).map((cred) => (
            <div key={cred.id}>{formatDate(cred.created_at || '')}</div>
          ))}
        </div>
      ),
    },
    {
      key: 'expires',
      header: 'Expires',
      align: 'center',
      sortValue: soonestExpiry,
      cellClassName: 'text-sm text-muted',
      render: (provider) => (
        <div className="space-y-2">
          {credsOf(provider).map((cred) => (
            <div key={cred.id}>{expiresCell(cred.expires_at)}</div>
          ))}
        </div>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'center',
      render: manageProviderCell,
    },
  ];

  return (
    <>
      <div className="px-4 py-6 sm:px-6 lg:px-8">
        <div className="sm:flex sm:items-center mb-8">
          <div className="sm:flex-auto">
            <h1 className="text-2xl font-semibold text-primary">
              {user?.role === 'super_admin' ? 'System Secrets' : 'Secrets'}
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
              {canManageSecrets && (
                <button
                  onClick={() => setActiveTab('organization')}
                  className={`tab whitespace-nowrap py-4 ${
                    activeTab === 'organization' ? 'tab-active' : 'tab-inactive'
                  }`}
                >
                  Organization Secrets ({orgTotalCount})
                </button>
              )}
            </nav>
          </div>
        )}

        {/* Organization Secrets Tab Content */}
        {canManageSecrets && (effectiveTab === 'organization' || !showTabs) && (
          <div>
            <ResourceTable<OrganizationSecret>
              data={filteredOrgSecrets}
              getItemId={(secret) => secret.id}
              columns={orgColumns}
              prefPage="secrets"
              pagination={{ itemLabel: 'secret' }}
              pageResetKey={orgSearchTerm}
              toolbar={
                <>
                  <SearchInput
                    value={orgSearchTerm}
                    onChange={setOrgSearchTerm}
                    placeholder="Search secrets..."
                  />
                  <Link
                    href={withReturnTo('/secrets/new', currentUrl)}
                    className="btn-primary inline-flex items-center"
                  >
                    <Plus className="mr-2 h-4 w-4" />
                    New Secret
                  </Link>
                </>
              }
              emptyState={
                <EmptyState
                  icon={<Key className="h-12 w-12" />}
                  title="No secrets found"
                  description={orgSearchTerm ? 'Try adjusting your search term.' : 'Get started by creating an organization secret.'}
                />
              }
            />
          </div>
        )}

        {/* Provider Credentials Tab Content */}
        {effectiveTab === 'providers' && showTabs && (
          <div>
            <ResourceTable<Provider>
              data={filteredProviders}
              getItemId={(provider) => provider.id}
              tieBreaker="provider"
              columns={providerColumns}
              prefPage="secrets-providers"
              pagination={{ itemLabel: 'provider' }}
              pageResetKey={providerSearchTerm}
              toolbar={
                <SearchInput
                  value={providerSearchTerm}
                  onChange={setProviderSearchTerm}
                  placeholder="Search providers and credentials..."
                />
              }
              emptyState={
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
              }
            />
          </div>
        )}
      </div>
    </>
  );
}
