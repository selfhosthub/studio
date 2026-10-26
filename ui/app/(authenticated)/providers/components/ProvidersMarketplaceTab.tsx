// ui/app/(authenticated)/providers/components/ProvidersMarketplaceTab.tsx

'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import Link from 'next/link';
import { MarketplacePackage, ProviderTier, ServiceType, SERVICE_TYPE_LABELS, SERVICE_TYPES } from '@/entities/provider';
import { getMarketplaceCatalog, getEntitlementTokenStatus, installPackageFromCatalog, reinstallPackage, uninstallPackage, removePackage, refreshProvidersCatalog } from '@/shared/api';
import { useUser } from '@/entities/user';
import { Download, Lock, Bug, RefreshCw, HelpCircle } from 'lucide-react';
import { ProviderDocsSlideOver } from '@/features/provider-docs/ProviderDocsSlideOver';
import {
  LinkedText,
  SearchInput,
  EmptyState,
  ResourceTable,
  type ResourceColumnConfig,
} from '@/shared/ui';
import { InstallAllDropdown, useCatalogStatus } from '@/features/marketplace';
import { useToast } from '@/features/toast';
import { useConfirm } from '@/shared/ui/ConfirmDialog';
import { deactivatedToast, useConfirmDeactivate } from './useConfirmDeactivate';
import { useConfirmRemove } from './useConfirmRemove';
import { providerWorkflowCount, removeBlockedReason } from './providerUsage';
import { useCurrentUrl, withReturnTo } from '@/shared/hooks/useReturnTo';
import { useListPref, isString, oneOf } from '@/shared/hooks/useListPref';

const TIER_FILTERS = ['all', 'community', 'plus'] as const;
const CATEGORY_FILTERS = ['all', ...SERVICE_TYPES] as const;
const STATUS_FILTERS = ['all', 'installed', 'deactivated', 'available'] as const;

/** Returns true when `latest` is a strictly newer semver than `installed`. */
function isNewerVersion(latest: string, installed: string): boolean {
  const parse = (v: string) => v.replace(/^v/, '').split('.').map(Number);
  const [aM, am, ap] = parse(latest);
  const [bM, bm, bp] = parse(installed);
  if (aM !== bM) return aM > bM;
  if (am !== bm) return am > bm;
  return (ap ?? 0) > (bp ?? 0);
}

interface ProvidersMarketplaceTabProps {
  isSuperAdmin: boolean;
}

export function ProvidersMarketplaceTab({ isSuperAdmin }: ProvidersMarketplaceTabProps) {
  const { user } = useUser();
  const { reportWarnings } = useCatalogStatus();
  const { toast } = useToast();
  const confirm = useConfirm();
  const confirmDeactivate = useConfirmDeactivate();
  const confirmRemove = useConfirmRemove();
  const from = useCurrentUrl();
  const [packages, setPackages] = useState<MarketplacePackage[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useListPref('providers-marketplace', 'search', '', isString);
  const [tierFilter, setTierFilter] = useListPref<'all' | ProviderTier>('providers-marketplace', 'tier', 'all', oneOf(TIER_FILTERS));
  const [categoryFilter, setCategoryFilter] = useListPref<'all' | ServiceType>('providers-marketplace', 'category', 'all', oneOf(CATEGORY_FILTERS));
  const [statusFilter, setStatusFilter] = useListPref<typeof STATUS_FILTERS[number]>('providers-marketplace', 'status', 'all', oneOf(STATUS_FILTERS));

  const [deactivating, setDeactivating] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [workflowCounts, setWorkflowCounts] = useState<Record<string, number>>({});

  // Install state
  const [installing, setInstalling] = useState<string | null>(null);
  const [tokenConfigured, setTokenConfigured] = useState<boolean>(false);

  // Bulk install state
  const [bulkInstalling, setBulkInstalling] = useState<'community' | 'plus' | null>(null);

  // Version selection modal

  // Refresh state
  const [refreshing, setRefreshing] = useState(false);

  // Provider docs slide-over
  const [docsSlug, setDocsSlug] = useState<string | null>(null);
  const [isDocsOpen, setIsDocsOpen] = useState(false);


  // Fetch catalog function - used for initial load and refresh
  const fetchCatalog = useCallback(async (showLoading = true) => {
    try {
      if (showLoading) setIsLoading(true);
      const [catalog, tokenStatus] = await Promise.all([
        getMarketplaceCatalog(),
        getEntitlementTokenStatus().catch(() => ({ configured: false })),
      ]);
      setPackages(catalog.packages);
      setTokenConfigured(tokenStatus.configured);
      reportWarnings(catalog.warnings || []);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch marketplace catalog:', err);
      setError('Failed to load marketplace. Please try again later.');
    } finally {
      if (showLoading) setIsLoading(false);
    }
  }, [reportWarnings]);

  useEffect(() => {
    // IIFE so the deferred setState inside fetchCatalog isn't read as a synchronous set.
    void (async () => { await fetchCatalog(); })();
  }, [fetchCatalog]);

  // Loads workflow usage for deactivated packages so Remove is disabled while workflows use them
  useEffect(() => {
    if (!isSuperAdmin) return;
    const ids = packages.filter(pkg => pkg.status === 'deactivated').map(pkg => pkg.id);
    if (ids.length === 0) return;
    let cancelled = false;
    void (async () => {
      const counts = await Promise.all(ids.map(id => providerWorkflowCount(id)));
      if (!cancelled) setWorkflowCounts(Object.fromEntries(ids.map((id, i) => [id, counts[i]])));
    })();
    return () => { cancelled = true; };
  }, [packages, isSuperAdmin]);

  // Get unique categories from packages
  const availableCategories = useMemo(() => {
    const categories = new Set(packages.map(pkg => pkg.category));
    return Array.from(categories).filter(cat => SERVICE_TYPES.includes(cat as ServiceType));
  }, [packages]);

  // Filters packages, ordered by name.
  const filteredPackages = useMemo(() => {
    return packages.filter(pkg => {
      if (tierFilter !== 'all' && pkg.tier !== tierFilter) return false;
      if (categoryFilter !== 'all' && pkg.category !== categoryFilter) return false;
      if (statusFilter !== 'all' && pkg.status !== statusFilter) return false;
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        return (
          pkg.display_name.toLowerCase().includes(query) ||
          pkg.description.toLowerCase().includes(query) ||
          pkg.services_preview.some(s => s.toLowerCase().includes(query))
        );
      }
      return true;
    }).sort((a, b) => a.display_name.localeCompare(b.display_name, undefined, { sensitivity: 'base' }));
  }, [packages, tierFilter, categoryFilter, statusFilter, searchQuery]);

  const handleDeactivate = async (pkg: MarketplacePackage) => {
    if (!(await confirmDeactivate(pkg.display_name, pkg.id))) return;

    setDeactivating(pkg.id);
    try {
      await uninstallPackage(pkg.id, true);
      toast(deactivatedToast(pkg.display_name));
      await fetchCatalog(false);
      setActionError(null);
    } catch (err: unknown) {
      console.error('Failed to deactivate package:', err);
      setActionError(err instanceof Error ? err.message : 'Failed to deactivate provider');
    } finally {
      setDeactivating(null);
    }
  };

  // Deletes a deactivated provider so it lists as available again.
  const handleRemove = async (pkg: MarketplacePackage) => {
    if (!(await confirmRemove(pkg.display_name, pkg.id))) return;

    setRemoving(pkg.id);
    try {
      await removePackage(pkg.id);
      toast({ title: `"${pkg.display_name}" removed`, variant: 'success' });
      await fetchCatalog(false);
      setActionError(null);
    } catch (err: unknown) {
      console.error('Failed to remove package:', err);
      toast({
        title: 'Remove failed',
        description: err instanceof Error ? err.message : 'Failed to remove provider',
        variant: 'destructive',
      });
    } finally {
      setRemoving(null);
    }
  };

  const handleInstallClick = async (pkg: MarketplacePackage) => {
    if (pkg.download_url) {
      handleInstallVersion(pkg);
    }
  };

  const handleInstallVersion = async (pkg: MarketplacePackage) => {
    setInstalling(pkg.id);
    setActionError(null);
    try {
      await installPackageFromCatalog(pkg.id);
      toast({
        title: pkg.status === 'installed' ? `"${pkg.display_name}" upgraded to v${pkg.version}` : `"${pkg.display_name}" installed`,
        variant: 'success',
      });
      await fetchCatalog(false);
    } catch (err: unknown) {
      console.error('Failed to install package:', err);
      setActionError(err instanceof Error ? err.message : 'Failed to install provider');
    } finally {
      setInstalling(null);
    }
  };

  // Reactivate a deactivated provider from the database (no download).
  const handleActivate = async (pkg: MarketplacePackage) => {
    setInstalling(pkg.id);
    setActionError(null);
    try {
      await reinstallPackage(pkg.id);
      toast({ title: `"${pkg.display_name}" activated`, variant: 'success' });
      await fetchCatalog(false);
    } catch (err: unknown) {
      console.error('Failed to activate package:', err);
      setActionError(err instanceof Error ? err.message : 'Failed to activate provider');
    } finally {
      setInstalling(null);
    }
  };

  // Check if package can be installed
  const canInstall = (pkg: MarketplacePackage) => {
    const hasDownload = (pkg.versions && pkg.versions.length > 0) || pkg.download_url || pkg.latest_url;
    if (!hasDownload) return false;
    if (pkg.tier === 'plus' && !tokenConfigured) return false;
    return true;
  };

  // Handle bulk install by tier
  const handleInstallAllByTier = async (tier: 'community' | 'plus') => {
    const available = packages.filter(pkg =>
      pkg.tier === tier && pkg.status === 'available' && canInstall(pkg)
    );
    if (!(await confirm({
      title: 'Install providers',
      message: `Install ${available.length} ${tier} provider${available.length !== 1 ? 's' : ''}?`,
      confirmLabel: 'Install',
    }))) return;

    setBulkInstalling(tier);
    setActionError(null);
    let installed = 0;
    for (const pkg of available) {
      try {
        await installPackageFromCatalog(pkg.id);
        installed++;
      } catch {
        // Continue installing remaining packages
      }
    }
    toast({ title: `Installed ${installed} of ${available.length} ${tier} providers`, variant: 'success' });
    await fetchCatalog(false);
    setBulkInstalling(null);
  };

  // Handle catalog refresh from remote
  const handleRefresh = async () => {
    setRefreshing(true);
    setActionError(null);
    try {
      const result = await refreshProvidersCatalog();
      toast({ description: result.message, variant: 'success' });
      await fetchCatalog(false);
    } catch (err: unknown) {
      console.error('Failed to refresh catalog:', err);
      setActionError(err instanceof Error ? err.message : 'Failed to refresh catalog');
    } finally {
      setRefreshing(false);
    }
  };

  // Get tier badge styling
  const getTierBadge = (tier: ProviderTier) => {
    switch (tier) {
      case 'plus':
        return { label: 'Plus', className: 'bg-warning-subtle text-warning' };
      case 'community':
      default:
        return { label: 'Community', className: 'bg-card text-primary' };
    }
  };

  // Get status badge styling
  const getStatusBadge = (status: MarketplacePackage['status']) => {
    switch (status) {
      case 'installed':
        return { label: 'active', className: 'bg-success-subtle text-success' };
      case 'deactivated':
        return { label: 'deactivated', className: 'bg-warning-subtle text-warning' };
      case 'available':
        return { label: 'available', className: 'bg-card text-primary' };
      default:
        return { label: status, className: 'bg-card text-primary' };
    }
  };

  const columns: ResourceColumnConfig<MarketplacePackage>[] = [
    {
      key: 'display_name',
      header: 'Provider',
      sortValue: (pkg) => pkg.display_name,
      render: (pkg) => (
        <div>
          <div className="text-sm font-medium flex items-center gap-1">
            {pkg.display_name}
            <button type="button" onClick={() => { setDocsSlug(pkg.id); setIsDocsOpen(true); }} className="text-muted hover:text-info transition-colors" title="Provider documentation">
              <HelpCircle className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="section-subtitle line-clamp-2">
            <LinkedText text={pkg.description} />
          </div>
        </div>
      ),
    },
    {
      key: 'category',
      header: 'Category',
      cellClassName: 'wrap-anywhere',
      align: 'center',
      sortValue: (pkg) => SERVICE_TYPE_LABELS[pkg.category as ServiceType] || pkg.category,
      render: (pkg) => (
        <span className="text-sm">
          {SERVICE_TYPE_LABELS[pkg.category as ServiceType] || pkg.category}
        </span>
      ),
    },
    {
      key: 'version',
      header: 'Version',
      align: 'center',
      sortValue: (pkg) => pkg.installed_version || pkg.version,
      render: (pkg) => (pkg.installed_version ? (
          <div className="flex flex-col items-center gap-0.5">
            <span className="text-sm text-success">v{pkg.installed_version}</span>
            {pkg.version && isNewerVersion(pkg.version, pkg.installed_version) && (
              <span className="text-xs text-warning font-medium" title={`Latest: v${pkg.version}`}>
                v{pkg.version} available
              </span>
            )}
          </div>
        ) : pkg.version ? (
          <span className="text-sm text-muted">v{pkg.version}</span>
        ) : (
          <span className="text-sm text-muted">-</span>
        )),
    },
    {
      key: 'tier',
      header: 'Tier',
      align: 'center',
      sortValue: (pkg) => getTierBadge(pkg.tier).label,
      render: (pkg) => (
        <span className={`badge ${getTierBadge(pkg.tier).className}`}>
          {getTierBadge(pkg.tier).label}
        </span>
      ),
    },
    {
      key: 'services',
      header: 'Services',
      align: 'center',
      sortValue: (pkg) => pkg.services_preview.length,
      render: (pkg) => (
        <div className="flex flex-wrap gap-1 max-w-xs justify-center">
          {pkg.services_preview.slice(0, 2).map((service, idx) => (
            <span
              key={idx}
              className="badge badge-default"
            >
              {service}
            </span>
          ))}
          {pkg.services_preview.length > 2 && (
            <span className="badge badge-default">
              +{pkg.services_preview.length - 2}
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      align: 'center',
      sortValue: (pkg) => getStatusBadge(pkg.status).label,
      render: (pkg) => (
        <span className={`badge ${getStatusBadge(pkg.status).className}`}>
          {getStatusBadge(pkg.status).label}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'center',
      render: (pkg) => (
        <div className="flex justify-center gap-2 items-center max-md:flex-col max-md:items-stretch">
          {pkg.status === 'installed' && pkg.provider_id && (
            <>
              <Link
                href={withReturnTo(`/providers/${pkg.provider_id}`, from)}
                className="action-btn-view"
              >
                View
              </Link>
              {user?.role === 'super_admin' && pkg.version && pkg.installed_version && isNewerVersion(pkg.version, pkg.installed_version) && (
                pkg.tier === 'plus' && !tokenConfigured ? (
                  <div className="flex flex-col items-center gap-1">
                    <span
                      className="action-btn-locked"
                      title="Upgrade requires entitlement token"
                    >
                      <Lock className="w-3 h-3 mr-1" />
                      Upgrade
                    </span>
                    <a
                      href="https://www.skool.com/selfhostinnovators"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs link"
                    >
                      Renew token
                    </a>
                  </div>
                ) : (
                  <button
                    onClick={() => handleInstallClick(pkg)}
                    disabled={installing === pkg.id}
                    className="action-btn-install"
                    title={`Upgrade to v${pkg.version}`}
                  >
                    {installing === pkg.id ? (
                      <>
                        <span className="animate-spin mr-1">⏳</span>
                        Upgrading...
                      </>
                    ) : (
                      <>
                        <Download className="w-3 h-3 mr-1" />
                        Upgrade
                      </>
                    )}
                  </button>
                )
              )}
              {user?.role === 'super_admin' && (
                <button
                  onClick={() => handleDeactivate(pkg)}
                  disabled={deactivating === pkg.id}
                  className="action-btn-warning disabled:opacity-50"
                >
                  {deactivating === pkg.id
                    ? 'Deactivating...'
                    : 'Deactivate'}
                </button>
              )}
              {pkg.bug_report_url && (
                <a
                  href={`${pkg.bug_report_url}?title=${encodeURIComponent(`[${pkg.display_name}] Bug Report`)}&body=${encodeURIComponent(`**Package:** ${pkg.display_name}\n**Version:** ${pkg.installed_version || 'unknown'}\n\n**Description:**\n\n**Steps to reproduce:**\n`)}`} // defaults-ok
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-secondary-sm"
                  title="Report a bug"
                >
                  <Bug className="w-3 h-3" />
                </a>
              )}
            </>
          )}
          {pkg.status === 'deactivated' && isSuperAdmin && (
            <>
              <button
                onClick={() => handleActivate(pkg)}
                disabled={installing === pkg.id}
                className="action-btn-install"
              >
                {installing === pkg.id ? (
                  <>
                    <span className="animate-spin mr-1">⏳</span>
                    Activating...
                  </>
                ) : (
                  'Activate'
                )}
              </button>
              <button
                onClick={() => handleRemove(pkg)}
                disabled={removing === pkg.id || !!removeBlockedReason(workflowCounts[pkg.id] ?? 0)}
                title={removeBlockedReason(workflowCounts[pkg.id] ?? 0) ?? undefined}
                className="action-btn-uninstall disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {removing === pkg.id ? 'Removing...' : 'Remove'}
              </button>
            </>
          )}
          {pkg.status === 'available' && isSuperAdmin && (
            <>
              {canInstall(pkg) ? (
                <button
                  onClick={() => handleInstallClick(pkg)}
                  disabled={installing === pkg.id}
                  className="action-btn-install"
                >
                  {installing === pkg.id ? (
                    <>
                      <span className="animate-spin mr-1">⏳</span>
                      Installing...
                    </>
                  ) : (
                    <>
                      <Download className="w-3 h-3 mr-1" />
                      Install
                    </>
                  )}
                </button>
              ) : pkg.tier === 'plus' && !tokenConfigured ? (
                <div className="flex flex-col items-center gap-1">
                  <span
                    className="action-btn-locked"
                    title="Plus provider - requires entitlement token"
                  >
                    <Lock className="w-3 h-3 mr-1" />
                    Plus
                  </span>
                  <a
                    href="https://www.skool.com/selfhostinnovators"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs link"
                  >
                    Get token from Skool
                  </a>
                </div>
              ) : (
                <span className="text-xs text-muted">
                  No download available
                </span>
              )}
            </>
          )}
          {(pkg.status === 'available' || pkg.status === 'deactivated') && !isSuperAdmin && (
            <span className="text-xs text-muted">
              Contact admin to {pkg.status === 'deactivated' ? 'activate' : 'install'}
            </span>
          )}
        </div>
      ),
    },
  ];

  return (
    <>
      {/* Action errors (install/uninstall/refresh) - dismissible, doesn't replace the table */}
      {actionError && !error && (
        <div className="mb-6 alert alert-warning flex items-start gap-3">
          <p className="alert-warning-text text-sm flex-1">{actionError}</p>
          <button
            onClick={() => setActionError(null)}
            className="link text-sm flex-shrink-0"
          >
            Dismiss
          </button>
        </div>
      )}

      <ResourceTable
        data={filteredPackages}
        getItemId={(pkg) => pkg.id}
        columns={columns}
        prefPage="providers-marketplace"
        pagination={{ itemLabel: 'provider' }}
        pageResetKey={`${searchQuery}|${tierFilter}|${categoryFilter}|${statusFilter}`}
        loading={isLoading}
        loadingMessage="Loading marketplace..."
        error={error}
        errorTitle="Error Loading Marketplace"
        onRetry={() => fetchCatalog()}
        emptyState={
          <EmptyState
            title="No providers found"
            description={
              searchQuery
                ? `No results for "${searchQuery}".`
                : tierFilter !== 'all' || categoryFilter !== 'all' || statusFilter !== 'all'
                ? 'Try adjusting your filters to see more providers.'
                : 'No providers are available yet.'
            }
            action={searchQuery ? (
              <button type="button" className="btn-secondary" onClick={() => setSearchQuery('')}>
                Clear search
              </button>
            ) : undefined}
          />
        }
        toolbar={
          <>
            <div className="w-full sm:w-auto sm:flex-1">
              <SearchInput
                value={searchQuery}
                onChange={setSearchQuery}
                placeholder="Search providers..."
              />
            </div>
            {isSuperAdmin && (
              <>
                {(packages.some(p => p.tier === 'community' && p.status === 'available' && canInstall(p)) ||
                  (tokenConfigured && packages.some(p => p.tier === 'plus' && p.status === 'available' && canInstall(p)))) && (
                  <InstallAllDropdown
                    hasCommunity={packages.some(p => p.tier === 'community' && p.status === 'available' && canInstall(p))}
                    hasPlus={tokenConfigured && packages.some(p => p.tier === 'plus' && p.status === 'available' && canInstall(p))}
                    installing={bulkInstalling}
                    onInstall={handleInstallAllByTier}
                  />
                )}
                <button
                  onClick={handleRefresh}
                  disabled={refreshing}
                  className="btn-primary inline-flex items-center justify-center gap-2"
                >
                  <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
                  {refreshing ? 'Refreshing...' : 'Refresh'}
                </button>
              </>
            )}
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value as 'all' | ServiceType)}
              className="form-select text-sm w-auto"
            >
              <option value="all">All Categories</option>
              {SERVICE_TYPES.map((type) => (
                <option key={type} value={type}>
                  {SERVICE_TYPE_LABELS[type]}
                </option>
              ))}
            </select>
            <select
              value={tierFilter}
              onChange={(e) => setTierFilter(e.target.value as 'all' | ProviderTier)}
              className="form-select text-sm w-auto"
            >
              <option value="all">All Tiers</option>
              <option value="community">Community</option>
              <option value="plus">Plus</option>
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as 'all' | 'installed' | 'deactivated' | 'available')}
              className="form-select text-sm w-auto"
            >
              <option value="all">All Statuses</option>
              <option value="installed">Active</option>
              <option value="deactivated">Deactivated</option>
              <option value="available">Available</option>
            </select>
          </>
        }
      />

      {/* Provider docs slide-over */}
      {docsSlug && (
        <ProviderDocsSlideOver
          slug={docsSlug}
          isOpen={isDocsOpen}
          onClose={() => setIsDocsOpen(false)}
        />
      )}
    </>
  );
}
