// ui/app/comfyui/marketplace/components/useComfyUIMarketplace.ts

import { useCallback, useEffect, useMemo, useState } from 'react';
import { PAGINATION } from '@/shared/lib/constants';
import {
  getComfyUICatalog,
  getInstalledComfyUI,
  installComfyUIWorkflow,
  uninstallComfyUIWorkflow,
  refreshComfyUICatalog,
} from '@/shared/api';
import type {
  MarketplaceComfyUI,
  InstalledComfyUIInfo,
  ComfyUIInstallResponse,
} from '@/shared/api';
import { useToast } from '@/features/toast';
import { useCatalogStatus } from '@/features/marketplace';

type SortField = 'display_name' | 'category' | 'tier';
type SortDirection = 'asc' | 'desc';

export type { SortField, SortDirection };

export function useComfyUIMarketplace() {
  const { toast } = useToast();
  const { reportWarnings } = useCatalogStatus();

  const [catalogWorkflows, setCatalogWorkflows] = useState<MarketplaceComfyUI[]>([]);
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());
  const [installedMap, setInstalledMap] = useState<Map<string, InstalledComfyUIInfo>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [uninstallingId, setUninstallingId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [tierFilter, setTierFilter] = useState<'all' | 'community' | 'plus'>('all');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGINATION.DEFAULT_PAGE_SIZE);
  const [sortField, setSortField] = useState<SortField>('display_name');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
  const [catalogFilterOptions, setCatalogFilterOptions] = useState<Record<string, string[]>>({
    tier: ['community', 'plus'],
    category: [],
  });
  const [uploading, setUploading] = useState(false);
  const [installAllInProgress, setInstallAllInProgress] = useState<'community' | 'plus' | null>(null);

  const markInstalled = (tplId: string, result: ComfyUIInstallResponse, version: string) => {
    setInstalledIds((prev) => new Set(prev).add(tplId));
    if (result.workflow_id && result.workflow_name) {
      setInstalledMap((prev) => {
        const next = new Map(prev);
        next.set(tplId, {
          id: tplId,
          name: result.workflow_name!,
          version,
        });
        return next;
      });
    }
  };

  const fetchMarketplace = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [catalog, installed] = await Promise.all([
        getComfyUICatalog(),
        getInstalledComfyUI().catch(() => ({
          installed_ids: [] as string[],
          installed_workflows: [] as InstalledComfyUIInfo[],
        })),
      ]);

      reportWarnings(catalog.warnings || []);

      setCatalogWorkflows(catalog.comfyui);

      setCatalogFilterOptions({
        tier: catalog.filter_options.tier,
        category: catalog.filter_options.category,
      });

      setInstalledIds(new Set(installed.installed_ids));
      const map = new Map<string, InstalledComfyUIInfo>();
      for (const wf of installed.installed_workflows || []) {
        map.set(wf.id, wf);
      }
      setInstalledMap(map);
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
    let result = catalogWorkflows.filter((t) => {
      if (tierFilter !== 'all' && t.tier !== tierFilter) return false;
      if (categoryFilter !== 'all' && t.category !== categoryFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          t.display_name.toLowerCase().includes(q) ||
          t.description.toLowerCase().includes(q)
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

  // Reset to first page when filters change (adjust during render, not in an effect).
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

  const handleInstall = async (tpl: MarketplaceComfyUI) => {
    setInstallingId(tpl.id);
    try {
      const result = await installComfyUIWorkflow(tpl.id);
      if (result.success) {
        toast({
          title: result.already_installed
            ? 'Already installed'
            : `"${result.workflow_name}" installed`,
          variant: 'success',
        });
        markInstalled(tpl.id, result, tpl.version);
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
      await uninstallComfyUIWorkflow(marketplaceId);
      toast({ title: `"${displayName}" removed`, variant: 'success' });
      setInstalledIds((prev) => {
        const next = new Set(prev);
        next.delete(marketplaceId);
        return next;
      });
      setInstalledMap((prev) => {
        const next = new Map(prev);
        next.delete(marketplaceId);
        return next;
      });
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

  const handleInstallAllByTier = async (tier: 'community' | 'plus') => {
    const notInstalled = catalogWorkflows.filter(
      (t) => !installedIds.has(t.id) && t.tier === tier
    );
    if (notInstalled.length === 0) {
      toast({ title: `All ${tier} workflows already installed`, variant: 'success' });
      return;
    }
    if (
      !window.confirm(
        `Install ${notInstalled.length} ${tier} workflow${notInstalled.length > 1 ? 's' : ''}?`
      )
    )
      return;

    setInstallAllInProgress(tier);
    let installed = 0;
    for (const tpl of notInstalled) {
      try {
        const result = await installComfyUIWorkflow(tpl.id);
        if (result.success && !result.already_installed) {
          installed++;
          markInstalled(tpl.id, result, tpl.version);
        }
      } catch {
        // Continue installing remaining workflows
      }
    }
    toast({
      title: `${installed} ${tier} workflow${installed !== 1 ? 's' : ''} installed`,
      variant: 'success',
    });
    setInstallAllInProgress(null);
  };

  const handleRefresh = async () => {
    setUploading(true);
    try {
      const result = await refreshComfyUICatalog();
      toast({ title: result.message, variant: 'success' });
      await fetchMarketplace();
    } catch (err: unknown) {
      toast({
        title: 'Failed to refresh catalog',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setUploading(false);
    }
  };

  return {
    catalogWorkflows,
    filteredCatalog,
    paginatedCatalog,
    installedIds,
    catalogFilterOptions,
    loading,
    error,
    page,
    setPage,
    pageSize,
    setPageSize,
    totalPages,
    search,
    setSearch,
    categoryFilter,
    setCategoryFilter,
    tierFilter,
    setTierFilter,
    sortField,
    sortDirection,
    handleSort,
    installingId,
    uninstallingId,
    uploading,
    installAllInProgress,
    handleInstall,
    handleUninstall,
    handleInstallAllByTier,
    handleRefresh,
    fetchMarketplace,
  };
}
