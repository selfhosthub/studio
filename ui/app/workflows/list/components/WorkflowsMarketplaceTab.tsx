// ui/app/workflows/list/components/WorkflowsMarketplaceTab.tsx

'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  getWorkflowDetail,
  getInstalledWorkflows,
  installWorkflowFromMarketplace,
  uninstallMarketplaceWorkflow,
  refreshWorkflowsCatalog,
  getEntitlementTokenStatus,
} from '@/shared/api';
import type {
  MarketplaceWorkflow,
  MarketplaceWorkflowDetail,
  InstalledWorkflowInfo,
} from '@/shared/api';
import { useToast } from '@/features/toast';
import { InstallAllDropdown, useCatalogStatus } from '@/features/marketplace';
import { WorkflowDetailModal } from './WorkflowDetailModal';
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
  const [bulkInstalling, setBulkInstalling] = useState<'community' | 'plus' | null>(null);
  const [uninstallingId, setUninstallingId] = useState<string | null>(null);
  const [viewWorkflow, setViewWorkflow] = useState<MarketplaceWorkflow | null>(null);
  const [viewDetail, setViewDetail] = useState<MarketplaceWorkflowDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [tokenConfigured, setTokenConfigured] = useState(false);

  // Org roles never need the entitlement token: their catalog only contains
  // platform-installed workflows, and org copy reads from package_versions.
  const plusUnlocked = !isSuperAdmin || tokenConfigured;

  // Catalog list omits the step DAG/connections to stay lean; fetch the full
  // workflow detail on row-click (super-admin pre-install view). A ref guards
  // against a slow earlier fetch overwriting a later one.
  const detailRequestRef = useRef<string | null>(null);
  const openWorkflow = async (wf: MarketplaceWorkflow) => {
    setViewWorkflow(wf);
    setViewDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    detailRequestRef.current = wf.id;
    try {
      const detail = await getWorkflowDetail(wf.id);
      if (detailRequestRef.current === wf.id) setViewDetail(detail);
    } catch (err: unknown) {
      if (detailRequestRef.current === wf.id) {
        setDetailError(err instanceof Error ? err.message : 'Failed to load detail');
      }
    } finally {
      if (detailRequestRef.current === wf.id) setDetailLoading(false);
    }
  };

  const closeWorkflow = () => {
    setViewWorkflow(null);
    setViewDetail(null);
    setDetailError(null);
  };
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [tierFilter, setTierFilter] = useState<'all' | 'community' | 'plus'>('all');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGINATION.DEFAULT_PAGE_SIZE);
  const [sortField, setSortField] = useState<SortField>('display_name');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
  const [filterOptions, setFilterOptions] = useState<Record<string, string[]>>({
    tier: ['community', 'plus'],
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
      const [catalog, tokenStatus] = await Promise.all([
        getWorkflowsCatalog(),
        getEntitlementTokenStatus().catch(() => ({ configured: false })),
        refreshInstalledWorkflows(),
      ]);
      setCatalogWorkflows(catalog.workflows);
      setTokenConfigured(tokenStatus.configured);
      setFilterOptions(catalog.filter_options);
      reportWarnings(catalog.warnings || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load marketplace catalog');
    } finally {
      setLoading(false);
    }
  }, [reportWarnings]);

  useEffect(() => {
    // IIFE so the deferred setState inside fetchMarketplace isn't read as a synchronous set.
    void (async () => { await fetchMarketplace(); })();
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
          const order: Record<string, number> = { community: 0, plus: 1 };
          cmp = (order[a.tier] ?? 2) - (order[b.tier] ?? 2);
          break;
        }
      }
      return sortDirection === 'asc' ? cmp : -cmp;
    });

    return result;
  }, [catalogWorkflows, search, categoryFilter, tierFilter, sortField, sortDirection]);

  // Reset to page 1 when filters change (adjust during render, not in an effect).
  const filterKey = `${search}|${categoryFilter}|${tierFilter}`;
  const [prevFilterKey, setPrevFilterKey] = useState(filterKey);
  if (filterKey !== prevFilterKey) {
    setPrevFilterKey(filterKey);
    setPage(1);
  }

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
      case 'plus':
        return {
          label: 'Plus',
          className: 'bg-warning-subtle text-warning',
        };
      case 'community':
      default:
        return {
          label: 'Community',
          className: 'bg-surface text-secondary',
        };
    }
  };

  const handleInstall = async (wf: MarketplaceWorkflow, opts?: { force?: boolean }) => {
    setInstallingId(wf.id);
    try {
      const result = await installWorkflowFromMarketplace(wf.id, { force: opts?.force });
      if (result.success) {
        const missingProviders = result.missing_packages ?? [];
        const missingPrompts = result.missing_prompts ?? [];
        const parts: string[] = [];
        if (missingProviders.length > 0) {
          parts.push(`providers: ${missingProviders.join(', ')}`);
        }
        if (missingPrompts.length > 0) {
          parts.push(`AI prompts: ${missingPrompts.join(', ')}`);
        }
        toast({
          title: result.already_installed
            ? 'Already installed'
            : `"${result.workflow_name}" installed`,
          description: parts.length > 0
            ? `Install before running - ${parts.join('; ')}`
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

  const handleInstallAllByTier = async (tier: 'community' | 'plus') => {
    const available = catalogWorkflows.filter(
      (wf) => wf.tier === tier && !installedIds.has(wf.id),
    );
    if (available.length === 0) {
      toast({ title: `All ${tier} workflows already installed`, variant: 'success' });
      return;
    }
    if (!window.confirm(`Install ${available.length} ${tier} workflow${available.length > 1 ? 's' : ''}?`)) return;

    setBulkInstalling(tier);
    let installed = 0;
    for (const wf of available) {
      try {
        const result = await installWorkflowFromMarketplace(wf.id);
        if (result.success && !result.already_installed) installed++;
      } catch {
        // Continue installing remaining workflows
      }
    }
    await refreshInstalledWorkflows();
    toast({
      title: `${installed} ${tier} workflow${installed !== 1 ? 's' : ''} installed`,
      variant: 'success',
    });
    setBulkInstalling(null);
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
        {isSuperAdmin && (
          <button
            onClick={handleRefreshCatalog}
            className="btn-primary inline-flex items-center justify-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        )}
        {(catalogWorkflows.some((wf) => wf.tier === 'community' && !installedIds.has(wf.id)) ||
          (plusUnlocked &&
            catalogWorkflows.some((wf) => wf.tier === 'plus' && !installedIds.has(wf.id)))) && (
          <InstallAllDropdown
            hasCommunity={catalogWorkflows.some(
              (wf) => wf.tier === 'community' && !installedIds.has(wf.id),
            )}
            hasPlus={
              plusUnlocked &&
              catalogWorkflows.some((wf) => wf.tier === 'plus' && !installedIds.has(wf.id))
            }
            installing={bulkInstalling}
            onInstall={handleInstallAllByTier}
          />
        )}
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
          onChange={(e) => setTierFilter(e.target.value as 'all' | 'community' | 'plus')}
          className="form-select text-sm w-auto"
        >
          <option value="all">All Tiers</option>
          <option value="community">Community</option>
          <option value="plus">Plus</option>
        </select>
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
          itemLabel="workflow"
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
                  <TableRow key={wf.id} onClick={() => openWorkflow(wf)}>
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
                      <div className="flex justify-center gap-2" onClick={(e) => e.stopPropagation()}>
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
                            <button
                              type="button"
                              onClick={() => handleInstall(wf, { force: true })}
                              disabled={installingId === wf.id}
                              className="action-btn-install"
                              title="Make another copy with a unique name; lets you edit one without losing the original."
                            >
                              {installingId === wf.id ? (
                                'Copying...'
                              ) : (
                                <>
                                  <Download className="w-3 h-3 mr-1" />
                                  Copy
                                </>
                              )}
                            </button>
                          )
                        ) : wf.tier === 'plus' && !plusUnlocked ? (
                          <span
                            className="action-btn-locked"
                            title="Plus workflow - requires entitlement token"
                          >
                            <Lock className="w-3 h-3 mr-1" />
                            Plus
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
            itemLabel="workflow"
            position="bottom"
          />
        </>
      )}

      <WorkflowDetailModal
        workflow={viewWorkflow}
        detail={viewDetail}
        loading={detailLoading}
        error={detailError}
        onClose={closeWorkflow}
      />
    </>
  );
}
