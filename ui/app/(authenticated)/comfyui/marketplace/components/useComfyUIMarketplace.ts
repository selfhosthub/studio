// ui/app/(authenticated)/comfyui/marketplace/components/useComfyUIMarketplace.ts

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useListPref, isString, oneOf } from '@/shared/hooks/useListPref';
import {
  getComfyUICatalog,
  getInstalledComfyUI,
  installComfyUIWorkflow,
  uninstallComfyUIWorkflow,
  refreshComfyUICatalog,
  setComfyUIVisibility,
} from '@/shared/api';
import type {
  MarketplaceComfyUI,
  InstalledComfyUIInfo,
  ComfyUIInstallResponse,
} from '@/shared/api';
import { useToast } from '@/features/toast';
import { useConfirm } from '@/shared/ui/ConfirmDialog';
import { useCatalogStatus } from '@/features/marketplace';

const TIER_FILTERS = ['all', 'community', 'plus'] as const;

export function useComfyUIMarketplace() {
  const { toast } = useToast();
  const confirm = useConfirm();
  const { reportWarnings } = useCatalogStatus();

  const [catalogWorkflows, setCatalogWorkflows] = useState<MarketplaceComfyUI[]>([]);
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());
  const [installedMap, setInstalledMap] = useState<Map<string, InstalledComfyUIInfo>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [uninstallingId, setUninstallingId] = useState<string | null>(null);
  const [search, setSearch] = useListPref('comfyui-marketplace', 'search', '', isString);
  const [categoryFilter, setCategoryFilter] = useListPref('comfyui-marketplace', 'category', 'all', isString);
  const [tierFilter, setTierFilter] = useListPref<typeof TIER_FILTERS[number]>('comfyui-marketplace', 'tier', 'all', oneOf(TIER_FILTERS));
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
          marketplace_id: tplId,
          workflow_id: result.workflow_id!,
          name: result.workflow_name!,
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
        getComfyUICatalog(undefined, undefined, true),
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
        map.set(wf.marketplace_id, wf);
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

  // Custom view: managed rows (uploads and visibility-managed packages),
  // including private ones the marketplace list never shows.
  const customWorkflows = useMemo(
    () => catalogWorkflows.filter((t) => t.origin === 'managed'),
    [catalogWorkflows]
  );

  // Filters the catalog, ordered by name. Private managed rows belong to the Custom view.
  const filteredCatalog = useMemo(() => {
    return catalogWorkflows.filter((t) => {
      if (t.origin === 'managed' && t.visibility === 'private') return false;
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
    }).sort((a, b) => a.display_name.localeCompare(b.display_name, undefined, { sensitivity: 'base' }));
  }, [catalogWorkflows, search, categoryFilter, tierFilter]);

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
    if (!(await confirm({
      title: 'Remove workflow',
      message: `Remove "${displayName}"?`,
      confirmLabel: 'Remove',
      variant: 'danger',
    }))) return;

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
      // Managed rows (uploads) cease to exist on remove; catalog rows stay
      // listed as not-installed.
      setCatalogWorkflows((rows) =>
        rows.filter((r) => !(r.id === marketplaceId && r.origin === 'managed'))
      );
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
      !(await confirm({
        title: 'Install workflows',
        message: `Install ${notInstalled.length} ${tier} workflow${notInstalled.length > 1 ? 's' : ''}?`,
        confirmLabel: 'Install',
      }))
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

  const handleSetVisibility = async (
    marketplaceId: string,
    visibility: 'private' | 'staging' | 'public'
  ) => {
    // Optimistic flip; the visibility route updates every version row.
    const prev = catalogWorkflows;
    setCatalogWorkflows((rows) =>
      rows.map((r) => (r.id === marketplaceId ? { ...r, visibility } : r))
    );
    try {
      await setComfyUIVisibility(marketplaceId, visibility);
      const name =
        catalogWorkflows.find((r) => r.id === marketplaceId)?.display_name || marketplaceId; // defaults-ok
      toast({ title: `"${name}" is now ${visibility}`, variant: 'success' });
    } catch (err: unknown) {
      setCatalogWorkflows(prev);
      toast({
        title: 'Failed to update visibility',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  return {
    catalogWorkflows,
    customWorkflows,
    filteredCatalog,
    installedIds,
    catalogFilterOptions,
    loading,
    error,
    search,
    setSearch,
    categoryFilter,
    setCategoryFilter,
    tierFilter,
    setTierFilter,
    installingId,
    uninstallingId,
    uploading,
    installAllInProgress,
    handleInstall,
    handleUninstall,
    handleInstallAllByTier,
    handleRefresh,
    handleSetVisibility,
    fetchMarketplace,
  };
}
