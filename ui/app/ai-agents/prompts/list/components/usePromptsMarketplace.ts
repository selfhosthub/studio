// ui/app/ai-agents/prompts/list/components/usePromptsMarketplace.ts

import { useCallback, useEffect, useMemo, useState } from 'react';
import { PAGINATION } from '@/shared/lib/constants';
import {
  getPromptsCatalog,
  getCustomPromptsCatalog,
  getInstalledPrompts,
  installPrompt,
  installCustomPrompt,
  uninstallPrompt,
  refreshPromptsCatalog,
  getEntitlementTokenStatus,
} from '@/shared/api';
import type {
  MarketplacePrompt,
  InstalledPromptInfo,
  PromptInstallResponse,
} from '@/shared/api';
import { useToast } from '@/features/toast';
import { useCatalogStatus } from '@/features/marketplace';

type SortField = 'display_name' | 'category' | 'tier';
type SortDirection = 'asc' | 'desc';

export type { SortField, SortDirection };

interface UsePromptsMarketplaceOptions {
  isSuperAdmin: boolean;
  onPromptsChanged: () => void;
}

export function usePromptsMarketplace({ isSuperAdmin, onPromptsChanged }: UsePromptsMarketplaceOptions) {
  const { toast } = useToast();
  const { reportWarnings } = useCatalogStatus();

  const [catalogPrompts, setCatalogPrompts] = useState<MarketplacePrompt[]>([]);
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());
  const [installedMap, setInstalledMap] = useState<Map<string, InstalledPromptInfo>>(new Map());
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
  const [catalogFilterOptions, setCatalogFilterOptions] = useState<Record<string, string[]>>({
    tier: ['basic', 'advanced'],
    category: [],
  });
  const [uploading, setUploading] = useState(false);
  const [installAllInProgress, setInstallAllInProgress] = useState<'basic' | 'advanced' | null>(null);
  const [tokenConfigured, setTokenConfigured] = useState(false);
  const [customPromptIds, setCustomPromptIds] = useState<Set<string>>(new Set());

  const markInstalled = (tplId: string, result: PromptInstallResponse, category: string) => {
    setInstalledIds((prev) => new Set(prev).add(tplId));
    if (result.prompt_id && result.prompt_name) {
      setInstalledMap((prev) => {
        const next = new Map(prev);
        next.set(tplId, {
          marketplace_id: tplId,
          prompt_id: result.prompt_id!,
          name: result.prompt_name!,
          category,
        });
        return next;
      });
    }
  };

  const fetchMarketplace = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [catalog, customCatalog, installed, tokenStatus] = await Promise.all([
        getPromptsCatalog(),
        getCustomPromptsCatalog().catch(() => ({
          version: '1.0.0',
          prompts: [] as MarketplacePrompt[],
          filter_options: { tier: [] as string[], category: [] as string[] },
        })),
        getInstalledPrompts().catch(() => ({
          installed_ids: [] as string[],
          installed_prompts: [] as InstalledPromptInfo[],
        })),
        getEntitlementTokenStatus().catch(() => ({ configured: false })),
      ]);
      setTokenConfigured(tokenStatus.configured);

      const customIds = new Set(customCatalog.prompts.map((t) => t.id));
      setCustomPromptIds(customIds);

      reportWarnings(catalog.warnings || []);

      const allPrompts = [...catalog.prompts, ...customCatalog.prompts];
      setCatalogPrompts(allPrompts);

      const allCategories = new Set([
        ...catalog.filter_options.category,
        ...customCatalog.filter_options.category,
      ]);
      setCatalogFilterOptions({
        tier: catalog.filter_options.tier,
        category: Array.from(allCategories).sort(),
      });

      setInstalledIds(new Set(installed.installed_ids));
      const map = new Map<string, InstalledPromptInfo>();
      for (const tpl of installed.installed_prompts || []) {
        map.set(tpl.marketplace_id, tpl);
      }
      setInstalledMap(map);
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
    let result = catalogPrompts.filter((t) => {
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
          const order: Record<string, number> = { basic: 0, advanced: 1 };
          cmp = (order[a.tier] ?? 2) - (order[b.tier] ?? 2);
          break;
        }
      }
      return sortDirection === 'asc' ? cmp : -cmp;
    });

    return result;
  }, [catalogPrompts, search, categoryFilter, tierFilter, sortField, sortDirection]);

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

  const handleInstall = async (tpl: MarketplacePrompt) => {
    setInstallingId(tpl.id);
    try {
      const isCustom = customPromptIds.has(tpl.id);
      const result = isCustom
        ? await installCustomPrompt(tpl.id)
        : await installPrompt(tpl.id);
      if (result.success) {
        toast({
          title: result.already_installed
            ? 'Already in organization'
            : `"${result.prompt_name}" copied to organization`,
          variant: 'success',
        });
        markInstalled(tpl.id, result, tpl.category);
        onPromptsChanged();
      }
    } catch (err: unknown) {
      toast({
        title: 'Failed to install prompt',
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
      await uninstallPrompt(marketplaceId);
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
      if (isSuperAdmin && customPromptIds.has(marketplaceId)) {
        setCatalogPrompts((prev) => prev.filter((t) => t.id !== marketplaceId));
        setCustomPromptIds((prev) => {
          const next = new Set(prev);
          next.delete(marketplaceId);
          return next;
        });
      }
      onPromptsChanged();
    } catch (err: unknown) {
      toast({
        title: 'Failed to uninstall prompt',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setUninstallingId(null);
    }
  };

  const handleInstallAllByTier = async (tier: 'basic' | 'advanced') => {
    const notInstalled = catalogPrompts.filter(
      (t) => !installedIds.has(t.id) && t.tier === tier
    );
    if (notInstalled.length === 0) {
      toast({ title: `All ${tier} prompts already installed`, variant: 'success' });
      return;
    }
    if (
      !window.confirm(
        `Install ${notInstalled.length} ${tier} prompt${notInstalled.length > 1 ? 's' : ''}?`
      )
    )
      return;

    setInstallAllInProgress(tier);
    let installed = 0;
    for (const tpl of notInstalled) {
      try {
        const isCustom = customPromptIds.has(tpl.id);
        const result = isCustom
          ? await installCustomPrompt(tpl.id)
          : await installPrompt(tpl.id);
        if (result.success && !result.already_installed) {
          installed++;
          markInstalled(tpl.id, result, tpl.category);
        }
      } catch {
        // Continue installing remaining prompts
      }
    }
    toast({
      title: `${installed} ${tier} prompt${installed !== 1 ? 's' : ''} installed`,
      variant: 'success',
    });
    onPromptsChanged();
    setInstallAllInProgress(null);
  };

  const handleRefresh = async () => {
    setUploading(true);
    try {
      const result = await refreshPromptsCatalog();
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
    catalogPrompts,
    filteredCatalog,
    paginatedCatalog,
    installedIds,
    catalogFilterOptions,
    tokenConfigured,
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
