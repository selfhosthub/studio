// ui/app/providers/components/ProvidersMarketplaceTab.tsx

'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import Link from 'next/link';
import { MarketplacePackage, PackageVersion, ProviderTier, ServiceType, SERVICE_TYPE_LABELS, SERVICE_TYPES } from '@/entities/provider';
import { getMarketplaceCatalog, getEntitlementTokenStatus, installPackageFromUrl, installPackageFromPath, uninstallPackage, checkPackageUsage, refreshProvidersCatalog } from '@/shared/api';
import { useUser } from '@/entities/user';
import { PAGINATION } from '@/shared/lib/constants';
import { ChevronDown, ChevronUp, Download, Lock, Bug, Upload, RefreshCw, HelpCircle } from 'lucide-react';
import { ProviderDocsSlideOver } from '@/features/provider-docs/ProviderDocsSlideOver';
import {
  LinkedText,
  SearchInput,
  Pagination,
  LoadingState,
  ErrorState,
  EmptyState,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableCell,
  TableHeaderCell,
  TableContainer,
} from '@/shared/ui';
import { VersionSelectModal, InstallAllDropdown, useCatalogStatus } from '@/features/marketplace';
import { useToast } from '@/features/toast';
import { PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';

type SortField = 'display_name' | 'category' | 'tier' | 'status';
type SortDirection = 'asc' | 'desc';

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
  const [packages, setPackages] = useState<MarketplacePackage[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [tierFilter, setTierFilter] = useState<'all' | ProviderTier>('all');
  const [categoryFilter, setCategoryFilter] = useState<'all' | ServiceType>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'installed' | 'deactivated' | 'available'>('all');

  // Sorting
  const [sortField, setSortField] = useState<SortField>('display_name');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(PAGINATION.DEFAULT_PAGE_SIZE);

  // Uninstall state
  const [uninstalling, setUninstalling] = useState<string | null>(null);

  // Install state
  const [installing, setInstalling] = useState<string | null>(null);
  const [tokenConfigured, setTokenConfigured] = useState<boolean>(false);

  // Bulk install state
  const [bulkInstalling, setBulkInstalling] = useState<'basic' | 'advanced' | null>(null);

  // Version selection modal
  const [versionSelectPackage, setVersionSelectPackage] = useState<MarketplacePackage | null>(null);

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
    fetchCatalog();
  }, [fetchCatalog]);

  // Get unique categories from packages
  const availableCategories = useMemo(() => {
    const categories = new Set(packages.map(pkg => pkg.category));
    return Array.from(categories).filter(cat => SERVICE_TYPES.includes(cat as ServiceType));
  }, [packages]);

  // Filter and sort packages
  const filteredPackages = useMemo(() => {
    let result = packages.filter(pkg => {
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
    });

    result.sort((a, b) => {
      let comparison = 0;
      switch (sortField) {
        case 'display_name':
          comparison = a.display_name.localeCompare(b.display_name);
          break;
        case 'category':
          comparison = a.category.localeCompare(b.category);
          break;
        case 'tier':
          const tierOrder: Record<ProviderTier, number> = { 'basic': 0, 'advanced': 1 };
          comparison = (tierOrder[a.tier] ?? 2) - (tierOrder[b.tier] ?? 2);
          break;
        case 'status':
          comparison = a.status.localeCompare(b.status);
          break;
      }
      return sortDirection === 'asc' ? comparison : -comparison;
    });

    return result;
  }, [packages, tierFilter, categoryFilter, statusFilter, searchQuery, sortField, sortDirection]);

  // Reset page when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, tierFilter, categoryFilter, statusFilter]);

  // Pagination calculations
  const totalCount = filteredPackages.length;
  const totalPages = Math.ceil(totalCount / pageSize) || 1;

  // Apply pagination
  const paginatedPackages = filteredPackages.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  );

  // Toggle sort
  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  // Handle uninstall with usage check and confirmation
  const handleUninstall = async (pkg: MarketplacePackage) => {
    try {
      const usage = await checkPackageUsage(pkg.id);
      if (usage.workflow_count > 0) {
        const orgCount = usage.affected_orgs?.length || 0;
        const warningMsg = `This package is used by ${usage.workflow_count} workflow(s) across ${orgCount} organization(s). Deactivating will break these. Continue?`;
        if (!confirm(warningMsg)) {
          return;
        }
      } else {
        if (!confirm(`Deactivate ${pkg.display_name}?`)) {
          return;
        }
      }
    } catch (err) {
      console.error('Failed to check package usage:', err);
      if (!confirm(`Deactivate ${pkg.display_name}?`)) {
        return;
      }
    }

    setUninstalling(pkg.id);
    try {
      await uninstallPackage(pkg.id, true);
      setPackages(prev => prev.map(p =>
        p.id === pkg.id
          ? { ...p, status: 'deactivated' as const, installed: false, installed_version: undefined }
          : p
      ));
      setActionError(null);
    } catch (err: unknown) {
      console.error('Failed to deactivate package:', err);
      setActionError(err instanceof Error ? err.message : 'Failed to deactivate package');
    } finally {
      setUninstalling(null);
    }
  };

  // Handle install button click - opens version selector if versions available
  const handleInstallClick = async (pkg: MarketplacePackage) => {
    if (pkg.versions && pkg.versions.length > 0) {
      setVersionSelectPackage(pkg);
    } else if (pkg.path) {
      setInstalling(pkg.id);
      setActionError(null);
      try {
        await installPackageFromPath(pkg.path, pkg.tier === 'advanced');
        await fetchCatalog(false);
      } catch (err: unknown) {
        setActionError(err instanceof Error ? err.message : 'Failed to install package');
      } finally {
        setInstalling(null);
      }
    } else if (pkg.download_url) {
      handleInstallVersion(pkg, { version: pkg.version || '1.0.0', download_url: pkg.download_url });
    }
  };

  // Handle install from selected version
  const handleInstallVersion = async (pkg: MarketplacePackage, version: PackageVersion) => {
    setVersionSelectPackage(null);
    setInstalling(pkg.id);
    setActionError(null);
    try {
      await installPackageFromUrl(version.download_url, pkg.tier === 'advanced');
      await fetchCatalog(false);
    } catch (err: unknown) {
      console.error('Failed to install package:', err);
      setActionError(err instanceof Error ? err.message : 'Failed to install package');
    } finally {
      setInstalling(null);
    }
  };

  // Check if package can be installed
  const canInstall = (pkg: MarketplacePackage) => {
    const hasDownload = (pkg.versions && pkg.versions.length > 0) || pkg.download_url || pkg.latest_url || pkg.path;
    if (!hasDownload) return false;
    if (pkg.tier === 'advanced' && !tokenConfigured) return false;
    return true;
  };

  // Handle bulk install by tier
  const handleInstallAllByTier = async (tier: 'basic' | 'advanced') => {
    const available = packages.filter(pkg =>
      pkg.tier === tier && pkg.status === 'available' && canInstall(pkg)
    );
    if (!confirm(`Install ${available.length} ${tier} package(s)?`)) return;

    setBulkInstalling(tier);
    setActionError(null);
    let installed = 0;
    for (const pkg of available) {
      try {
        if (pkg.path) {
          await installPackageFromPath(pkg.path, pkg.tier === 'advanced');
          installed++;
        } else {
          const url = pkg.latest_url || pkg.download_url || pkg.versions?.[0]?.download_url;
          if (url) {
            await installPackageFromUrl(url, pkg.tier === 'advanced');
            installed++;
          }
        }
      } catch {
        // Continue installing remaining packages
      }
    }
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
      case 'advanced':
        return { label: 'Advanced', className: 'bg-warning-subtle text-warning' };
      case 'basic':
      default:
        return { label: 'Basic', className: 'bg-card text-primary' };
    }
  };

  // Get status badge styling
  const getStatusBadge = (status: MarketplacePackage['status']) => {
    switch (status) {
      case 'installed':
        return { label: 'Active', className: 'bg-success-subtle text-success' };
      case 'deactivated':
        return { label: 'Deactivated', className: 'bg-warning-subtle text-warning' };
      case 'available':
        return { label: 'Available', className: 'bg-card text-primary' };
      default:
        return { label: status, className: 'bg-card text-primary' };
    }
  };

  // Sort indicator component
  const SortIndicator = ({ field }: { field: SortField }) => {
    if (sortField !== field) return null;
    return sortDirection === 'asc' ? (
      <ChevronUp className="inline w-4 h-4 ml-1" />
    ) : (
      <ChevronDown className="inline w-4 h-4 ml-1" />
    );
  };

  return (
    <>
      {/* Super admin header controls */}
      {isSuperAdmin && (
        <div className="flex items-center gap-2 mb-6">
          {(packages.some(p => p.tier === 'basic' && p.status === 'available' && canInstall(p)) ||
            (tokenConfigured && packages.some(p => p.tier === 'advanced' && p.status === 'available' && canInstall(p)))) && (
            <InstallAllDropdown
              hasBasic={packages.some(p => p.tier === 'basic' && p.status === 'available' && canInstall(p))}
              hasAdvanced={tokenConfigured && packages.some(p => p.tier === 'advanced' && p.status === 'available' && canInstall(p))}
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
            {refreshing ? 'Refreshing...' : 'Refresh Catalog'}
          </button>
          <Link
            href="/providers/create"
            className="btn-primary inline-flex items-center justify-center gap-2"
          >
            <Upload size={16} />
            Upload Provider
          </Link>
        </div>
      )}

      {/* Search row */}
      <div className="mb-6 flex flex-wrap gap-3 items-center">
        <div className="w-full sm:w-auto sm:flex-1">
          <SearchInput
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder="Search providers..."
          />
        </div>
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
          <option value="basic">Basic</option>
          <option value="advanced">Advanced</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as 'all' | 'installed' | 'deactivated' | 'available')}
          className="form-select text-sm w-auto"
        >
          <option value="all">All Status</option>
          <option value="installed">Active</option>
          <option value="deactivated">Deactivated</option>
          <option value="available">Available</option>
        </select>
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          totalCount={totalCount}
          pageSize={pageSize}
          onPageChange={setCurrentPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setCurrentPage(1);
          }}
          pageSizeOptions={PAGE_SIZE_OPTIONS}
          position="top"
          itemLabel="package"
        />
      </div>

      {isLoading && (
        <LoadingState message="Loading marketplace..." />
      )}

      {!isLoading && error && (
        <ErrorState
          title="Error Loading Marketplace"
          message={error}
          onRetry={() => fetchCatalog()}
          retryLabel="Try Again"
        />
      )}

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

      {!isLoading && !error && filteredPackages.length === 0 && (
        <EmptyState
          title="No Packages Found"
          description={
            searchQuery || tierFilter !== 'all' || categoryFilter !== 'all' || statusFilter !== 'all'
              ? 'Try adjusting your filters to see more packages.'
              : 'No packages are available yet.'
          }
        />
      )}

      {!isLoading && !error && paginatedPackages.length > 0 && (
        <>
        <TableContainer>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHeaderCell onClick={() => handleSort('display_name')}>
                  Package
                  <SortIndicator field="display_name" />
                </TableHeaderCell>
                <TableHeaderCell align="center" onClick={() => handleSort('category')}>
                  Category
                  <SortIndicator field="category" />
                </TableHeaderCell>
                <TableHeaderCell align="center">
                  Version
                </TableHeaderCell>
                <TableHeaderCell align="center" onClick={() => handleSort('tier')}>
                  Tier
                  <SortIndicator field="tier" />
                </TableHeaderCell>
                <TableHeaderCell align="center">
                  Services
                </TableHeaderCell>
                <TableHeaderCell align="center" onClick={() => handleSort('status')}>
                  Status
                  <SortIndicator field="status" />
                </TableHeaderCell>
                <TableHeaderCell align="center">
                  Actions
                </TableHeaderCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {paginatedPackages.map((pkg) => (
                <TableRow key={pkg.id}>
                  <TableCell>
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
                  </TableCell>
                  <TableCell align="center">
                    <span className="text-sm">
                      {SERVICE_TYPE_LABELS[pkg.category as ServiceType] || pkg.category}
                    </span>
                  </TableCell>
                  <TableCell align="center">
                    {pkg.installed_version ? (
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
                    )}
                  </TableCell>
                  <TableCell align="center">
                    <span className={`badge ${getTierBadge(pkg.tier).className}`}>
                      {getTierBadge(pkg.tier).label}
                    </span>
                  </TableCell>
                  <TableCell align="center">
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
                  </TableCell>
                  <TableCell align="center">
                    <span className={`badge ${getStatusBadge(pkg.status).className}`}>
                      {getStatusBadge(pkg.status).label}
                    </span>
                  </TableCell>
                  <TableCell align="center">
                    <div className="flex justify-center gap-2">
                      {pkg.status === 'installed' && pkg.provider_id && (
                        <>
                          <Link
                            href={`/providers/${pkg.provider_id}`}
                            className="action-btn-view"
                          >
                            View
                          </Link>
                          {user?.role === 'super_admin' && pkg.version && pkg.installed_version && isNewerVersion(pkg.version, pkg.installed_version) && (
                            pkg.tier === 'advanced' && !tokenConfigured ? (
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
                              onClick={() => handleUninstall(pkg)}
                              disabled={uninstalling === pkg.id}
                              className="action-btn-warning disabled:opacity-50"
                            >
                              {uninstalling === pkg.id
                                ? 'Deactivating...'
                                : 'Deactivate'}
                            </button>
                          )}
                          {pkg.bug_report_url && (
                            <a
                              href={`${pkg.bug_report_url}?title=${encodeURIComponent(`[${pkg.display_name}] Bug Report`)}&body=${encodeURIComponent(`**Package:** ${pkg.display_name}\n**Version:** ${pkg.installed_version || 'unknown'}\n\n**Description:**\n\n**Steps to reproduce:**\n`)}`}
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
                        <button
                          onClick={() => handleInstallClick(pkg)}
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
                          ) : pkg.tier === 'advanced' && !tokenConfigured ? (
                            <div className="flex flex-col items-center gap-1">
                              <span
                                className="action-btn-locked"
                                title="Advanced package - requires entitlement token"
                              >
                                <Lock className="w-3 h-3 mr-1" />
                                Advanced
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
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>

        {/* Pagination Controls - Bottom */}
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          totalCount={totalCount}
          pageSize={pageSize}
          onPageChange={setCurrentPage}
          itemLabel="package"
          position="bottom"
        />
        </>
      )}

      {/* Version Selection Modal */}
      {versionSelectPackage && (
        <VersionSelectModal
          package={versionSelectPackage}
          onClose={() => setVersionSelectPackage(null)}
          onInstall={(version) => handleInstallVersion(versionSelectPackage, version)}
          isInstalling={installing === versionSelectPackage.id}
        />
      )}

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
