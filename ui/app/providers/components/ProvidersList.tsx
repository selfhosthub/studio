// ui/app/providers/components/ProvidersList.tsx

'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { Provider, ProviderTier } from '@/entities/provider';
import Link from 'next/link';
import {
  StatusBadge,
  ActionButton,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableCell,
  TableHeaderCell,
  TableContainer,
  SearchInput,
  Pagination,
  LoadingState,
  ErrorState,
  EmptyState,
} from '@/shared/ui';
import { useUser } from '@/entities/user';
import { uninstallPackage, checkPackageUsage, getProviders } from '@/shared/api';
import { LayoutGrid, List, Plug, HelpCircle } from 'lucide-react';
import { ProviderDocsSlideOver } from '@/features/provider-docs/ProviderDocsSlideOver';
import { PAGE_SIZE_OPTIONS, getStoredPageSize } from '@/shared/lib/pagination';
import { listPageSizeKey } from '@/shared/lib/constants';

const PAGE_SIZE_KEY = listPageSizeKey('providers');

type ViewMode = 'grid' | 'table';

interface ProvidersListProps {
  providerTypeFilter?: string;
}

export default function ProvidersList({ providerTypeFilter }: ProvidersListProps) {
  const { user } = useUser();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uninstalling, setUninstalling] = useState<string | null>(null);

  // Search and pagination state
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(() => getStoredPageSize(PAGE_SIZE_KEY));
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [docsSlug, setDocsSlug] = useState<string | null>(null);
  const [isDocsOpen, setIsDocsOpen] = useState(false);

  // Load view mode preference
  useEffect(() => {
    const saved = localStorage.getItem('providers-view-mode');
    if (saved === 'grid' || saved === 'table') {
      setViewMode(saved);
    }
  }, []);

  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode);
    localStorage.setItem('providers-view-mode', mode);
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

  // Filter providers based on type and search
  const filteredProviders = useMemo(() => {
    return providers.filter((provider) => {
      // Apply type filter first (e.g. super_admin Custom tab only shows custom providers)
      if (providerTypeFilter && provider.provider_type?.toLowerCase() !== providerTypeFilter.toLowerCase()) {
        return false;
      }
      // Then apply search
      return (
        provider.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        provider.description?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        provider.provider_type?.toLowerCase().includes(searchTerm.toLowerCase())
      );
    });
  }, [providers, searchTerm, providerTypeFilter]);

  // Reset page when search changes
  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm]);

  // Pagination calculations
  const totalCount = filteredProviders.length;
  const totalPages = Math.ceil(totalCount / pageSize) || 1;

  // Apply pagination
  const paginatedProviders = filteredProviders.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  );

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
        title={isSuperAdmin ? "No Custom Providers" : "No Providers Found"}
        description={isSuperAdmin
          ? "Upload a custom provider package to make it available for organizations."
          : "Get started by installing providers from the marketplace."}
        action={isSuperAdmin ? (
          <Link
            href="/providers/create"
            className="btn-primary inline-flex items-center"
          >
            Upload Package
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
      case 'advanced':
        return { label: 'Advanced', className: 'bg-warning-subtle text-warning' };
      case 'basic':
      default:
        return { label: 'Basic', className: 'bg-card text-primary' };
    }
  };

  const handleUninstall = async (provider: Provider) => {
    const packageName = provider.slug || provider.name.toLowerCase().replace(/\s+/g, '-');

    // Check usage and confirm
    try {
      const usage = await checkPackageUsage(packageName);
      if (usage.workflow_count > 0) {
        const orgCount = usage.affected_orgs?.length || 0;
        const warningMsg = `This package is used by ${usage.workflow_count} workflow(s) across ${orgCount} organization(s). Deactivating will break these. Continue?`;
        if (!confirm(warningMsg)) {
          return;
        }
      } else {
        if (!confirm(`Deactivate ${provider.name}?`)) {
          return;
        }
      }
    } catch (err) {
      console.error('Failed to check package usage:', err);
      if (!confirm(`Deactivate ${provider.name}?`)) {
        return;
      }
    }

    // Proceed with uninstall (force=true since user confirmed)
    setUninstalling(provider.id);
    try {
      await uninstallPackage(packageName, true);
      setProviders(prev => prev.filter(p => p.id !== provider.id));
    } catch (err: unknown) {
      console.error('Failed to deactivate package:', err);
      setError(err instanceof Error ? err.message : 'Failed to deactivate package');
    } finally {
      setUninstalling(null);
    }
  };

  return (
    <div>
      {/* Search and View Controls */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
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
        {/* Pagination Controls - Top */}
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          totalCount={totalCount}
          pageSize={pageSize}
          onPageChange={setCurrentPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setCurrentPage(1);
            localStorage.setItem(PAGE_SIZE_KEY, String(size));
          }}
          pageSizeOptions={PAGE_SIZE_OPTIONS}
          position="top"
        />
      </div>

      {/* Empty state for filtered results */}
      {filteredProviders.length === 0 && searchTerm && (
        <EmptyState
          title="No providers found"
          description="Try adjusting your search term."
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
                        href={`/providers/${provider.id}`}
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
                      status={provider.status || 'active'}
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
                  href={`/providers/${provider.id}`}
                  className="link text-sm font-medium"
                >
                  View Details
                </Link>
                <div className="flex space-x-3">
                  {user?.role === 'admin' && (
                    <Link
                      href={`/providers/${provider.id}/credentials`}
                      className="text-sm font-medium text-success hover:text-success"
                    >
                      Credentials
                    </Link>
                  )}
                  {isSuperAdmin && (
                    <button
                      onClick={() => handleUninstall(provider)}
                      disabled={uninstalling === provider.id}
                      className="text-sm font-medium link-subtle disabled:opacity-50"
                    >
                      {uninstalling === provider.id
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
      {viewMode === 'table' && paginatedProviders.length > 0 && (
        <TableContainer>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHeaderCell>Provider</TableHeaderCell>
                <TableHeaderCell align="center">Type</TableHeaderCell>
                <TableHeaderCell align="center">Version</TableHeaderCell>
                <TableHeaderCell align="center">Tier</TableHeaderCell>
                <TableHeaderCell align="center">Services</TableHeaderCell>
                <TableHeaderCell align="center">Status</TableHeaderCell>
                <TableHeaderCell align="center">Actions</TableHeaderCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {paginatedProviders.map((provider) => (
                <TableRow key={provider.id}>
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <div className={`flex-shrink-0 w-10 h-10 rounded-lg ${getAvatarGradient(provider.name)} flex items-center justify-center`}>
                        <span className="text-white font-bold text-sm">
                          {getInitials(provider.name)}
                        </span>
                      </div>
                      <div>
                        <div className="flex items-center gap-1">
                          <Link
                            href={`/providers/${provider.id}`}
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
                  </TableCell>
                  <TableCell align="center">
                    <span className={`badge ${getProviderTypeColor(provider.provider_type)}`}>
                      {provider.provider_type}
                    </span>
                  </TableCell>
                  <TableCell align="center">
                    <span className="text-sm text-muted">
                      {provider.client_metadata?.package_version ? `v${provider.client_metadata.package_version}` : '-'}
                    </span>
                  </TableCell>
                  <TableCell align="center">
                    <span className={`badge ${getTierBadge(provider.tier)?.className}`}>
                      {getTierBadge(provider.tier)?.label}
                    </span>
                  </TableCell>
                  <TableCell align="center">
                    {provider.services?.length || 0}
                  </TableCell>
                  <TableCell align="center">
                    <StatusBadge
                      status={provider.status || 'active'}
                      variant={
                        provider.status === "active"
                          ? "success"
                          : provider.status === "inactive"
                            ? "warning"
                            : "error"
                      }
                    />
                  </TableCell>
                  <TableCell align="center">
                    <div className="flex justify-center gap-2">
                      <ActionButton
                        variant="navigate"
                        onClick={() => window.location.href = `/providers/${provider.id}`}
                      >
                        View
                      </ActionButton>
                      {user?.role === 'admin' && (
                        <ActionButton
                          variant="change"
                          onClick={() => window.location.href = `/providers/${provider.id}/credentials`}
                        >
                          Credentials
                        </ActionButton>
                      )}
                      {isSuperAdmin && (
                        <ActionButton
                          variant="destructive"
                          onClick={() => handleUninstall(provider)}
                          disabled={uninstalling === provider.id}
                        >
                          {uninstalling === provider.id
                            ? 'Uninstalling...'
                            : 'Uninstall'}
                        </ActionButton>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Pagination Controls - Bottom */}
      {paginatedProviders.length > 0 && (
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
