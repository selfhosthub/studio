// ui/app/workflows/list/components/WorkflowsMarketplaceTab.tsx

'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PAGINATION } from '@/shared/lib/constants';
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHeader,
  TableHeaderCell,
  TableRow,
  SearchInput,
  Pagination,
  LoadingState,
  ErrorState,
  EmptyState,
} from '@/shared/ui';
import {
  getWorkflowsCatalog,
  getInstalledWorkflows,
  installWorkflowFromMarketplace,
  uninstallMarketplaceWorkflow,
  refreshWorkflowsCatalog,
} from '@/shared/api';
import type {
  MarketplaceWorkflow,
  InstalledWorkflowInfo,
} from '@/shared/api';
import { useToast } from '@/features/toast';
import { useCatalogStatus } from '@/features/marketplace';
import { PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';
import {
  Download,
  Trash2,
  RefreshCw,
  Lock,
  ChevronUp,
  ChevronDown,
} from 'lucide-react';

type SortField = 'display_name' | 'category' | 'tier';
type SortDirection = 'asc' | 'desc';

interface WorkflowsMarketplaceTabProps {
  isSuperAdmin: boolean;
}

export function WorkflowsMarketplaceTab({ isSuperAdmin }: WorkflowsMarketplaceTabProps) {
  const { toast } = useToast();
  const { reportWarnings } = useCatalogStatus();

  const [catalogWorkflows, setCatalogWorkflows] = useState<MarketplaceWorkflow[]>([]);
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());
  const [installedMap, setInstalledMap] = useState<Map<string, InstalledWorkflowInfo>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [uninstallingId, setUninstallingId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [tierFilter, setTierFilter] = useState<'all' | 'basic' | 'advanced'>('all');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGINATION.DEFAULT_PAGE_SIZE);
  const [sortField, setSortField] = useState<SortField>('display_name');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
  const [filterOptions, setFilterOptions] = useState<Record<string, string[]>>({
    tier: ['basic', 'advanced'],
    category: [],
  });

  const refreshInstalledWorkflows = async () => {
    const installed = await getInstalledWorkflows().catch(() => ({
      installed_ids: [] as string[],
      installed_workflows: [] as InstalledWorkflowInfo[],
    }));
    setInstalledIds(new Set(installed.installed_ids));
    const map = new Map<string, InstalledWorkflowInfo>();
    for (const wf of installed.installed_workflows || []) {
      map.set(wf.marketplace_id, wf);
    }
    setInstalledMap(map);
  };

  const fetchMarketplace = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [catalog] = await Promise.all([
        getWorkflowsCatalog(),
        refreshInstalledWorkflows(),
      ]);
      setCatalogWorkflows(catalog.workflows);
      setFilterOptions(catalog.filter_options);
      reportWarnings(catalog.warnings || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load marketplace catalog');
    } finally {
      setLoading(false);
    }
  }, [reportWarnings]);

  useEffect(() => {
    fetchMarketplace();
  }, [fetchMarketplace]);

  // Filter + sort + paginate
  const filteredCatalog = useMemo(() => {
    let result = catalogWorkflows.filter((w) => {
      if (tierFilter !== 'all' && w.tier !== tierFilter) return false;
      if (categoryFilter !== 'all' && w.category !== categoryFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          w.display_name.toLowerCase().includes(q) ||
          w.description.toLowerCase().includes(q)
        );
      }
      return true;
    });

    result.sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'display_name':
          cmp = a.display_name.localeCompare(b.display_name);
          break;
        case 'category':
          cmp = a.category.localeCompare(b.category);
          break;
        case 'tier': {
          const order: Record<string, number> = { basic: 0, advanced: 1 };
          cmp = (order[a.tier] ?? 2) - (order[b.tier] ?? 2);
          break;
        }
      }
      return sortDirection === 'asc' ? cmp : -cmp;
    });

    return result;
  }, [catalogWorkflows, search, categoryFilter, tierFilter, sortField, sortDirection]);

  useEffect(() => {
    setPage(1);
  }, [search, categoryFilter, tierFilter]);

  const totalPages = Math.ceil(filteredCatalog.length / pageSize) || 1;
  const paginatedCatalog = filteredCatalog.slice(
    (page - 1) * pageSize,
    page * pageSize
  );

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const sortIcon = (field: SortField) => {
    if (sortField !== field) return null;
    return sortDirection === 'asc'
      ? <ChevronUp className="inline w-4 h-4 ml-1" />
      : <ChevronDown className="inline w-4 h-4 ml-1" />;
  };

  const getTierBadge = (tier: string) => {
    switch (tier) {
      case 'advanced':
        return {
          label: 'Advanced',
          className: 'bg-warning-subtle text-warning',
        };
      case 'basic':
      default:
        return {
          label: 'Basic',
          className: 'bg-surface text-secondary',
        };
    }
  };

  const handleInstall = async (wf: MarketplaceWorkflow) => {
    setInstallingId(wf.id);
    try {
      const result = await installWorkflowFromMarketplace(wf.id);
      if (result.success) {
        const missingProviders = result.missing_packages ?? [];
        const missingPrompts = result.missing_prompts ?? [];
        const parts: string[] = [];
        if (missingProviders.length > 0) {
          parts.push(`providers: ${missingProviders.join(', ')}`);
        }
        if (missingPrompts.length > 0) {
          parts.push(`AI agent prompts: ${missingPrompts.join(', ')}`);
        }
        toast({
          title: result.already_installed
            ? 'Already installed'
            : `"${result.workflow_name}" installed`,
          description: parts.length > 0
            ? `Install before running — ${parts.join('; ')}`
            : undefined,
          variant: 'success',
          persistent: parts.length > 0,
        });
        await refreshInstalledWorkflows();
      }
    } catch (err: unknown) {
      toast({
        title: 'Failed to install workflow',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setInstallingId(null);
    }
  };

  const handleUninstall = async (marketplaceId: string) => {
    const info = installedMap.get(marketplaceId);
    const displayName = info?.name || marketplaceId;
    if (!window.confirm(`Remove "${displayName}"?`)) return;

    setUninstallingId(marketplaceId);
    try {
      await uninstallMarketplaceWorkflow(marketplaceId);
      toast({ title: `"${displayName}" removed`, variant: 'success' });
      await refreshInstalledWorkflows();
    } catch (err: unknown) {
      toast({
        title: 'Failed to uninstall workflow',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setUninstallingId(null);
    }
  };

  const handleRefreshCatalog = async () => {
    try {
      const result = await refreshWorkflowsCatalog();
      toast({ title: result.message, variant: 'success' });
      await fetchMarketplace();
    } catch (err: unknown) {
      toast({
        title: 'Failed to refresh catalog',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  return (
    <>
      {/* Search + Filters + Pagination */}
      <div className="mb-6 flex flex-wrap gap-3 items-center">
        <div className="w-full sm:w-auto sm:flex-1">
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Search marketplace..."
          />
        </div>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="form-select text-sm w-auto"
        >
          <option value="all">All Categories</option>
          {filterOptions.category.map((cat) => (
            <option key={cat} value={cat}>
              {cat.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
            </option>
          ))}
        </select>
        <select
          value={tierFilter}
          onChange={(e) => setTierFilter(e.target.value as 'all' | 'basic' | 'advanced')}
          className="form-select text-sm w-auto"
        >
          <option value="all">All Tiers</option>
          <option value="basic">Basic</option>
          <option value="advanced">Advanced</option>
        </select>
        {isSuperAdmin && (
          <button
            onClick={handleRefreshCatalog}
            className="btn-primary inline-flex items-center justify-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh Catalog
          </button>
        )}
        <Pagination
          currentPage={page}
          totalPages={totalPages}
          totalCount={filteredCatalog.length}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setPage(1);
          }}
          pageSizeOptions={PAGE_SIZE_OPTIONS}
          position="top"
          itemLabel="workflows"
        />
      </div>

      {loading && <LoadingState message="Loading marketplace catalog..." />}

      {!loading && error && (
        <ErrorState title="Error" message={error} onRetry={fetchMarketplace} />
      )}

      {!loading && !error && filteredCatalog.length === 0 && (
        <EmptyState
          title="No Workflows Found"
          description={
            search || tierFilter !== 'all' || categoryFilter !== 'all'
              ? 'Try adjusting your filters to see more workflows.'
              : 'No workflows are available yet.'
          }
        />
      )}

      {!loading && !error && paginatedCatalog.length > 0 && (
        <>
          <TableContainer>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell onClick={() => handleSort('display_name')}>
                    Workflow
                    {sortIcon('display_name')}
                  </TableHeaderCell>
                  <TableHeaderCell align="center" onClick={() => handleSort('category')}>
                    Category
                    {sortIcon('category')}
                  </TableHeaderCell>
                  <TableHeaderCell align="center" onClick={() => handleSort('tier')}>
                    Tier
                    {sortIcon('tier')}
                  </TableHeaderCell>
                  <TableHeaderCell align="center">Actions</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paginatedCatalog.map((wf) => (
                  <TableRow key={wf.id}>
                    <TableCell>
                      <div>
                        <div className="text-sm font-medium">
                          {wf.display_name}
                          {wf.version && (
                            <span className="ml-2 text-xs text-muted">v{wf.version}</span>
                          )}
                        </div>
                        <div className="section-subtitle line-clamp-2">
                          {wf.description}
                        </div>
                        {!wf.requirements_met && (wf.missing_packages.length > 0 || (wf.missing_prompts ?? []).length > 0) && (
                          <div className="text-xs text-warning mt-1">
                            Requires:{' '}
                            {[
                              ...wf.missing_packages,
                              ...(wf.missing_prompts ?? []).map(p => `prompt:${p}`),
                            ].join(', ')}
                          </div>
                        )}
                      </div>
                    </TableCell>
                    <TableCell align="center">
                      <span className="text-sm">
                        {wf.category.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                      </span>
                    </TableCell>
                    <TableCell align="center">
                      <span className={`badge${getTierBadge(wf.tier).className}`}>
                        {getTierBadge(wf.tier).label}
                      </span>
                    </TableCell>
                    <TableCell align="center">
                      <div className="flex justify-center gap-2">
                        {installedIds.has(wf.id) ? (
                          isSuperAdmin ? (
                            <button
                              type="button"
                              onClick={() => handleUninstall(wf.id)}
                              disabled={uninstallingId === wf.id}
                              className="action-btn-uninstall"
                            >
                              {uninstallingId === wf.id ? (
                                'Removing...'
                              ) : (
                                <>
                                  <Trash2 className="w-3 h-3 mr-1" />
                                  Remove
                                </>
                              )}
                            </button>
                          ) : (
                            <span className="text-xs text-success font-medium">
                              Installed
                            </span>
                          )
                        ) : wf.tier === 'advanced' ? (
                          <span
                            className="action-btn-locked"
                            title="Advanced workflow - requires entitlement token"
                          >
                            <Lock className="w-3 h-3 mr-1" />
                            Advanced
                          </span>
                        ) : (
                          <button
                            type="button"
                            onClick={() => handleInstall(wf)}
                            disabled={installingId === wf.id}
                            className="action-btn-install"
                          >
                            {installingId === wf.id ? (
                              'Installing...'
                            ) : (
                              <>
                                <Download className="w-3 h-3 mr-1" />
                                {isSuperAdmin ? 'Install' : 'Copy'}
                              </>
                            )}
                          </button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <Pagination
            currentPage={page}
            totalPages={totalPages}
            totalCount={filteredCatalog.length}
            pageSize={pageSize}
            onPageChange={setPage}
            itemLabel="workflows"
            position="bottom"
          />
        </>
      )}
    </>
  );
}
