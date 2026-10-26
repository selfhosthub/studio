// ui/app/(authenticated)/providers/components/ProvidersList.tsx

'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Provider,
  ProviderTier,
  Visibility,
  VISIBILITY_LABELS,
  isCustomOriginSlug,
} from '@/entities/provider';
import Link from 'next/link';
import {
  StatusBadge,
  ActionButton,
  ResourceTable,
  sortRows,
  resolveTieBreak,
  SearchInput,
  Pagination,
  LoadingState,
  ErrorState,
  EmptyState,
  type ResourceColumnConfig,
  type SortDirection,
  type SortState,
} from '@/shared/ui';
import { useUser } from '@/entities/user';
import { useToast } from '@/features/toast';
import { uninstallPackage, reinstallPackage, getProviders, updateProvider } from '@/shared/api';
import { LayoutGrid, List, Plug, HelpCircle } from 'lucide-react';
import { ProviderDocsSlideOver } from '@/features/provider-docs/ProviderDocsSlideOver';
import { PAGE_SIZE_OPTIONS, DEFAULT_PAGE_SIZE } from '@/shared/lib/pagination';
import { STORAGE_KEYS } from '@/shared/lib/constants';
import { useCurrentUrl, withReturnTo } from '@/shared/hooks/useReturnTo';
import { deactivatedToast, useConfirmDeactivate } from './useConfirmDeactivate';
import { useListPref, isPageSize, isString, oneOf } from '@/shared/hooks/useListPref';

type ViewMode = 'grid' | 'table';

const SORT_DIRECTIONS = ['asc', 'desc'] as const;

// Package name for a provider: its slug, else its name hyphenated.
function packageNameOf(provider: Provider): string {
  return provider.slug || provider.name.toLowerCase().replace(/\s+/g, '-');
}

// Status label for a provider; an inactive provider reads as deactivated.
function statusLabel(provider: Provider): string {
  if (provider.status === 'inactive') return 'deactivated';
  return provider.status || 'active'; // defaults-ok
}

interface ProvidersListProps {
  // Show only managed/custom-origin providers (non-reserved namespace).
  customOriginOnly?: boolean;
}

export default function ProvidersList({ customOriginOnly }: ProvidersListProps) {
  const { user } = useUser();
  const from = useCurrentUrl();
  const confirmDeactivate = useConfirmDeactivate();
  const { toast } = useToast();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deactivating, setDeactivating] = useState<string | null>(null);
  const [activating, setActivating] = useState<string | null>(null);

  // Search and pagination state
  const [searchTerm, setSearchTerm] = useListPref('providers', 'search', '', isString);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useListPref('providers', 'pageSize', DEFAULT_PAGE_SIZE, isPageSize);
  const [sortField, setSortField] = useListPref('providers', 'sortField', '', isString);
  const [sortDirection, setSortDirection] = useListPref<SortDirection>('providers', 'sortDirection', 'asc', oneOf(SORT_DIRECTIONS));
  const [viewMode, setViewMode] = useState<ViewMode>('table');
  const [docsSlug, setDocsSlug] = useState<string | null>(null);
  const [isDocsOpen, setIsDocsOpen] = useState(false);

  // Load view mode preference (Pattern D: ref-flag + compute-then-set at top level).
  const didInitViewMode = useRef(false);
  useEffect(() => {
    if (didInitViewMode.current) return;
    didInitViewMode.current = true;
    const saved = localStorage.getItem(STORAGE_KEYS.PROVIDERS_VIEW_MODE);
    // Compute unconditionally; fall back to 'table' so setViewMode is a direct top-level statement.
    const next: ViewMode = (saved === 'grid' || saved === 'table') ? (saved as ViewMode) : 'table';
    setViewMode(next);
  }, []);

  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode);
    localStorage.setItem(STORAGE_KEYS.PROVIDERS_VIEW_MODE, mode);
  };

  useEffect(() => {
    async function fetchProviders() {
      try {
        setIsLoading(true);
        const data = await getProviders();
        setProviders(data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch providers:', err);
        setError('Failed to load providers. Please try again later.');
      } finally {
        setIsLoading(false);
      }
    }

    fetchProviders();
  }, []);

  const filteredProviders = useMemo(() => {
    return providers
      .filter((provider) => {
        if (customOriginOnly && !isCustomOriginSlug(provider.slug)) {
          return false;
        }
        return (
          provider.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
          provider.description?.toLowerCase().includes(searchTerm.toLowerCase()) ||
          provider.provider_type?.toLowerCase().includes(searchTerm.toLowerCase())
        );
      })
      .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
  }, [providers, searchTerm, customOriginOnly]);

  // Reset page when search changes (adjust during render, not in an effect).
  const [prevSearchTerm, setPrevSearchTerm] = useState(searchTerm);
  if (searchTerm !== prevSearchTerm) {
    setPrevSearchTerm(searchTerm);
    setCurrentPage(1);
  }

  if (isLoading) {
    return <LoadingState message="Loading providers..." />;
  }

  if (error) {
    return (
      <ErrorState
        title="Error Loading Providers"
        message={error}
        onRetry={() => window.location.reload()}
        retryLabel="Try Again"
      />
    );
  }

  const isSuperAdmin = user?.role === 'super_admin';

  if (filteredProviders.length === 0 && !searchTerm) {
    return (
      <EmptyState
        icon={<Plug className="h-12 w-12" />}
        title={isSuperAdmin ? "No custom providers" : "No providers found"}
        description={isSuperAdmin
          ? "Upload a custom provider to make it available for organizations."
          : "Get started by installing providers from the Marketplace."}
        action={isSuperAdmin ? (
          <Link
            href="/providers/create"
            className="btn-primary inline-flex items-center"
          >
            Upload Provider
          </Link>
        ) : undefined}
      />
    );
  }

  // Helper functions
  const getInitials = (name: string) => {
    return name.substring(0, 2).toUpperCase();
  };

  const getAvatarGradient = (name: string) => {
    const gradients = [
      'bg-gradient-to-br from-blue-400 to-blue-600',
      'bg-gradient-to-br from-purple-400 to-purple-600',
      'bg-gradient-to-br from-green-400 to-green-600',
      'bg-gradient-to-br from-orange-400 to-orange-600',
      'bg-gradient-to-br from-pink-400 to-pink-600',
      'bg-gradient-to-br from-indigo-400 to-indigo-600',
    ];
    const index = name.charCodeAt(0) % gradients.length;
    return gradients[index];
  };

  const getProviderTypeColor = (type: string) => {
    switch (type) {
      case 'api':
        return 'bg-info-subtle text-info';
      case 'webhook':
        return 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300';
      case 'notification':
        return 'bg-success-subtle text-success';
      default:
        return 'bg-surface text-secondary';
    }
  };

  const getTierBadge = (tier?: string) => {
    switch (tier) {
      case 'plus':
        return { label: 'Plus', className: 'bg-warning-subtle text-warning' };
      case 'community':
      default:
        return { label: 'Community', className: 'bg-card text-primary' };
    }
  };

  const handleDeactivate = async (provider: Provider) => {
    const packageName = packageNameOf(provider);
    if (!(await confirmDeactivate(provider.name, packageName))) return;

    setDeactivating(provider.id);
    try {
      await uninstallPackage(packageName, true);
      setProviders(prev => prev.map(p => (p.id === provider.id ? { ...p, status: 'inactive' } : p)));
      toast(deactivatedToast(provider.name));
    } catch (err: unknown) {
      console.error('Failed to deactivate package:', err);
      setError(err instanceof Error ? err.message : 'Failed to deactivate provider');
    } finally {
      setDeactivating(null);
    }
  };

  const handleActivate = async (provider: Provider) => {
    setActivating(provider.id);
    try {
      await reinstallPackage(packageNameOf(provider));
      setProviders(prev => prev.map(p => (p.id === provider.id ? { ...p, status: 'active' } : p)));
      toast({ title: `"${provider.name}" activated`, variant: 'success' });
    } catch (err: unknown) {
      console.error('Failed to activate package:', err);
      setError(err instanceof Error ? err.message : 'Failed to activate provider');
    } finally {
      setActivating(null);
    }
  };

  const handleVisibilityChange = async (provider: Provider, visibility: Visibility) => {
    const previous = provider.visibility;
    setProviders(prev =>
      prev.map(p => (p.id === provider.id ? { ...p, visibility } : p))
    );
    try {
      await updateProvider(provider.id, { visibility });
    } catch (err: unknown) {
      console.error('Failed to update visibility:', err);
      setError(err instanceof Error ? err.message : 'Failed to update visibility');
      setProviders(prev =>
        prev.map(p => (p.id === provider.id ? { ...p, visibility: previous } : p))
      );
    }
  };

  const columns: ResourceColumnConfig<Provider>[] = [
    {
      key: 'name',
      header: 'Provider',
      sortValue: (provider) => provider.name,
      render: (provider) => (
        <div className="flex items-center gap-3">
          <div className={`flex-shrink-0 w-10 h-10 rounded-lg ${getAvatarGradient(provider.name)} flex items-center justify-center max-md:hidden`}>
            <span className="text-white font-bold text-sm">
              {getInitials(provider.name)}
            </span>
          </div>
          <div>
            <div className="flex items-center gap-1">
              <Link
                href={withReturnTo(`/providers/${provider.id}`, from)}
                className="text-sm font-medium link hover:underline"
              >
                {provider.name}
              </Link>
              {!!(provider.client_metadata as Record<string, unknown>)?.slug && (
                <button type="button" onClick={() => { setDocsSlug((provider.client_metadata as Record<string, unknown>).slug as string); setIsDocsOpen(true); }} className="text-muted hover:text-info transition-colors" title="Provider documentation">
                  <HelpCircle className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            <div className="text-xs text-muted line-clamp-2">
              {provider.description}
            </div>
          </div>
        </div>
      ),
    },
    {
      key: 'type',
      header: 'Type',
      align: 'center',
      sortValue: (provider) => provider.provider_type,
      render: (provider) => (
        <span className={`badge ${getProviderTypeColor(provider.provider_type)}`}>
          {provider.provider_type}
        </span>
      ),
    },
    {
      key: 'version',
      header: 'Version',
      align: 'center',
      sortValue: (provider) => (provider.client_metadata?.package_version ? String(provider.client_metadata.package_version) : null),
      render: (provider) => (
        <span className="text-sm text-muted">
          {provider.client_metadata?.package_version ? `v${provider.client_metadata.package_version}` : '-'}
        </span>
      ),
    },
    {
      key: 'tier',
      header: 'Tier',
      align: 'center',
      sortValue: (provider) => getTierBadge(provider.tier)?.label,
      render: (provider) => (
        <span className={`badge ${getTierBadge(provider.tier)?.className}`}>
          {getTierBadge(provider.tier)?.label}
        </span>
      ),
    },
    {
      key: 'services',
      header: 'Services',
      align: 'center',
      sortValue: (provider) => provider.services?.length,
      render: (provider) => provider.services?.length || 0,
    },
    {
      key: 'status',
      header: 'Status',
      align: 'center',
      sortValue: (provider) => statusLabel(provider),
      render: (provider) => (
        <StatusBadge
          status={statusLabel(provider)}
          variant={
            provider.status === "active"
              ? "success"
              : provider.status === "inactive"
                ? "warning"
                : "error"
          }
        />
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'center',
      render: (provider) => (
        <div className="flex justify-center gap-2 items-center max-md:flex-col max-md:items-stretch">
          {isSuperAdmin && isCustomOriginSlug(provider.slug) && (
            <select
              aria-label="Visibility"
              value={provider.visibility ?? 'private'} // defaults-ok
              onChange={(e) =>
                handleVisibilityChange(provider, e.target.value as Visibility)
              }
              className="form-input text-sm py-1"
            >
              {(Object.keys(VISIBILITY_LABELS) as Visibility[]).map((v) => (
                <option key={v} value={v}>
                  {VISIBILITY_LABELS[v]}
                </option>
              ))}
            </select>
          )}
          <ActionButton
            variant="navigate"
            onClick={() => window.location.href = withReturnTo(`/providers/${provider.id}`, from)}
          >
            View
          </ActionButton>
          {user?.role === 'admin' && (
            <ActionButton
              variant="change"
              onClick={() => window.location.href = withReturnTo(`/providers/${provider.id}/credentials`, from)}
            >
              Credentials
            </ActionButton>
          )}
          {isSuperAdmin && provider.status === 'inactive' && (
            <ActionButton
              variant="active"
              onClick={() => handleActivate(provider)}
              disabled={activating === provider.id}
            >
              {activating === provider.id ? 'Activating...' : 'Activate'}
            </ActionButton>
          )}
          {isSuperAdmin && provider.status !== 'inactive' && (
            <ActionButton
              variant="warning"
              onClick={() => handleDeactivate(provider)}
              disabled={deactivating === provider.id}
            >
              {deactivating === provider.id
                ? 'Deactivating...'
                : 'Deactivate'}
            </ActionButton>
          )}
        </div>
      ),
    },
  ];

  const activeSortColumn = columns.find((c) => c.key === sortField && c.sortValue);
  const sortedProviders = activeSortColumn?.sortValue
    ? sortRows(filteredProviders, activeSortColumn.sortValue, sortDirection, (provider) => provider.id, resolveTieBreak(columns))
    : filteredProviders;

  const handleSortChange = (next: SortState) => {
    setSortField(next.field ?? '');
    setSortDirection(next.direction);
    setCurrentPage(1);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
  };

  // Pagination shared by the grid and table views
  const totalCount = sortedProviders.length;
  const totalPages = Math.ceil(totalCount / pageSize) || 1; // defaults-ok
  const paginatedProviders = sortedProviders.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  );

  const viewControls = (
    <>
      <div className="w-full sm:w-auto sm:flex-1">
        <SearchInput
          value={searchTerm}
          onChange={setSearchTerm}
          placeholder="Search providers..."
        />
      </div>
      {/* View Toggle */}
      <div className="flex items-center gap-1 bg-card rounded-lg p-1">
        <button
          onClick={() => handleViewModeChange('grid')}
          className={`p-2 rounded ${
            viewMode === 'grid'
              ? 'bg-card shadow text-primary'
              : 'text-secondary hover:text-secondary'
          }`}
          title="Grid view"
        >
          <LayoutGrid className="w-4 h-4" />
        </button>
        <button
          onClick={() => handleViewModeChange('table')}
          className={`p-2 rounded ${
            viewMode === 'table'
              ? 'bg-card shadow text-primary'
              : 'text-secondary hover:text-secondary'
          }`}
          title="Table view"
        >
          <List className="w-4 h-4" />
        </button>
      </div>
    </>
  );

  return (
    <div>
      {/* Search, view toggle and top pager for the grid view */}
      {viewMode === 'grid' && (
        <div className="flex flex-wrap items-center gap-3 mb-6">
          {viewControls}
          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            totalCount={totalCount}
            pageSize={pageSize}
            onPageChange={setCurrentPage}
            onPageSizeChange={handlePageSizeChange}
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            position="top"
          />
        </div>
      )}

      {/* Empty state for filtered results */}
      {viewMode === 'grid' && filteredProviders.length === 0 && searchTerm && (
        <EmptyState
          title="No providers found"
          description={`No results for "${searchTerm}".`}
          action={
            <button type="button" className="btn-secondary" onClick={() => setSearchTerm('')}>
              Clear search
            </button>
          }
        />
      )}

      {/* Grid View */}
      {viewMode === 'grid' && paginatedProviders.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {paginatedProviders.map((provider) => (
            <div
              key={provider.id}
              className="card-interactive flex flex-col overflow-hidden"
            >
              <div className="p-5 flex-1">
                <div className="flex items-start gap-4 mb-4">
                  <div className={`flex-shrink-0 w-12 h-12 rounded-lg ${getAvatarGradient(provider.name)} flex items-center justify-center`}>
                    <span className="text-white font-bold text-lg">
                      {getInitials(provider.name)}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1 mb-1">
                      <Link
                        href={withReturnTo(`/providers/${provider.id}`, from)}
                        className="link text-sm font-medium"
                      >
                        {provider.name}
                      </Link>
                      {!!(provider.client_metadata as Record<string, unknown>)?.slug && (
                        <button type="button" onClick={() => { setDocsSlug((provider.client_metadata as Record<string, unknown>).slug as string); setIsDocsOpen(true); }} className="text-muted hover:text-info transition-colors" title="Provider documentation">
                          <HelpCircle className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                    <StatusBadge
                      status={statusLabel(provider)}
                      variant={
                        provider.status === "active"
                          ? "success"
                          : provider.status === "inactive"
                            ? "warning"
                            : "error"
                      }
                    />
                  </div>
                </div>

                <div className="flex flex-wrap gap-2 mb-3">
                  <span className={`badge ${getProviderTypeColor(provider.provider_type)}`}>
                    {provider.provider_type}
                  </span>
                  {!!provider.client_metadata?.package_version && (
                    <span className="badge badge-default">
                      v{String(provider.client_metadata.package_version)}
                    </span>
                  )}
                  {getTierBadge(provider.tier) && (
                    <span className={`badge ${getTierBadge(provider.tier)!.className}`}>
                      {getTierBadge(provider.tier)!.label}
                    </span>
                  )}
                </div>

                <p className="text-secondary text-sm mb-4 line-clamp-2">
                  {provider.description}
                </p>

                {provider.services && provider.services.length > 0 && (
                  <div className="mb-4">
                    <p className="text-xs text-secondary mb-1">
                      Services: {provider.services.length}
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {provider.services.slice(0, 3).map((service) => (
                        <span
                          key={service.id}
                          className="badge badge-default"
                          title={service.description || ''}
                        >
                          {service.display_name}
                        </span>
                      ))}
                      {provider.services.length > 3 && (
                        <span className="badge badge-default">
                          +{provider.services.length - 3} more
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>

              <div className="card-footer flex justify-between items-center">
                <Link
                  href={withReturnTo(`/providers/${provider.id}`, from)}
                  className="link text-sm font-medium"
                >
                  View
                </Link>
                <div className="flex space-x-3">
                  {user?.role === 'admin' && (
                    <Link
                      href={withReturnTo(`/providers/${provider.id}/credentials`, from)}
                      className="text-sm font-medium text-success hover:text-success"
                    >
                      Credentials
                    </Link>
                  )}
                  {isSuperAdmin && isCustomOriginSlug(provider.slug) && (
                    <select
                      aria-label="Visibility"
                      value={provider.visibility ?? 'private'} // defaults-ok
                      onChange={(e) =>
                        handleVisibilityChange(provider, e.target.value as Visibility)
                      }
                      className="form-input text-sm py-1"
                    >
                      {(Object.keys(VISIBILITY_LABELS) as Visibility[]).map((v) => (
                        <option key={v} value={v}>
                          {VISIBILITY_LABELS[v]}
                        </option>
                      ))}
                    </select>
                  )}
                  {isSuperAdmin && provider.status === 'inactive' && (
                    <button
                      onClick={() => handleActivate(provider)}
                      disabled={activating === provider.id}
                      className="text-sm font-medium link disabled:opacity-50"
                    >
                      {activating === provider.id ? 'Activating...' : 'Activate'}
                    </button>
                  )}
                  {isSuperAdmin && provider.status !== 'inactive' && (
                    <button
                      onClick={() => handleDeactivate(provider)}
                      disabled={deactivating === provider.id}
                      className="text-sm font-medium text-warning hover:underline disabled:opacity-50"
                    >
                      {deactivating === provider.id
                        ? 'Deactivating...'
                        : 'Deactivate'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Table View */}
      {viewMode === 'table' && (
        <ResourceTable
          data={paginatedProviders}
          getItemId={(provider) => provider.id}
          columns={columns}
          sort={{
            field: activeSortColumn ? activeSortColumn.key : null,
            direction: sortDirection,
            onChange: handleSortChange,
            server: true,
          }}
          pagination={{
            itemLabel: 'provider',
            server: {
              currentPage,
              totalCount,
              pageSize,
              onPageChange: setCurrentPage,
              onPageSizeChange: handlePageSizeChange,
            },
          }}
          toolbar={viewControls}
          emptyState={
            <EmptyState
              title="No providers found"
              description={searchTerm ? `No results for "${searchTerm}".` : 'Try adjusting your search term.'}
              action={searchTerm ? (
                <button type="button" className="btn-secondary" onClick={() => setSearchTerm('')}>
                  Clear search
                </button>
              ) : undefined}
            />
          }
        />
      )}

      {/* Pagination Controls - Bottom */}
      {viewMode === 'grid' && paginatedProviders.length > 0 && (
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          totalCount={totalCount}
          pageSize={pageSize}
          onPageChange={setCurrentPage}
          itemLabel="provider"
          position="bottom"
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
    </div>
  );
}
