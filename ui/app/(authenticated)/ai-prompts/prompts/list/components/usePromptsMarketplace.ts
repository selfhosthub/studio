// ui/app/(authenticated)/ai-prompts/prompts/list/components/usePromptsMarketplace.ts

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useListPref, isString, oneOf } from '@/shared/hooks/useListPref';
import {
  getPromptsCatalog,
  getInstalledPrompts,
  installPrompt,
  uninstallPrompt,
  getMarketplacePromptUsage,
  refreshPromptsCatalog,
  getEntitlementTokenStatus,
} from '@/shared/api';
import type {
  MarketplacePrompt,
  InstalledPromptInfo,
  PromptInstallResponse,
} from '@/shared/api';
import { useToast } from '@/features/toast';
import { useConfirm } from '@/shared/ui/ConfirmDialog';
import { useCatalogStatus } from '@/features/marketplace';

const TIER_FILTERS = ['all', 'community', 'plus'] as const;

interface UsePromptsMarketplaceOptions {
  onPromptsChanged: () => void;
  isSuperAdmin?: boolean;
}

export function usePromptsMarketplace({ onPromptsChanged, isSuperAdmin = false }: UsePromptsMarketplaceOptions) {
  const { toast } = useToast();
  const confirm = useConfirm();
  const { reportWarnings } = useCatalogStatus();

  const [catalogPrompts, setCatalogPrompts] = useState<MarketplacePrompt[]>([]);
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());
  const [installedMap, setInstalledMap] = useState<Map<string, InstalledPromptInfo>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [uninstallingId, setUninstallingId] = useState<string | null>(null);
  const [search, setSearch] = useListPref('prompts-marketplace', 'search', '', isString);
  const [categoryFilter, setCategoryFilter] = useListPref('prompts-marketplace', 'category', 'all', isString);
  const [tierFilter, setTierFilter] = useListPref<typeof TIER_FILTERS[number]>('prompts-marketplace', 'tier', 'all', oneOf(TIER_FILTERS));
  const [catalogFilterOptions, setCatalogFilterOptions] = useState<Record<string, string[]>>({
    tier: ['community', 'plus'],
    category: [],
  });
  const [uploading, setUploading] = useState(false);
  const [installAllInProgress, setInstallAllInProgress] = useState<'community' | 'plus' | null>(null);
  const [tokenConfigured, setTokenConfigured] = useState(false);

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
      const [catalog, installed, tokenStatus] = await Promise.all([
        getPromptsCatalog(),
        getInstalledPrompts().catch(() => ({
          installed_ids: [] as string[],
          installed_prompts: [] as InstalledPromptInfo[],
        })),
        getEntitlementTokenStatus().catch(() => ({ configured: false })),
      ]);
      setTokenConfigured(tokenStatus.configured);

      reportWarnings(catalog.warnings || []);

      // The merged catalog already folds in the super-org's managed (published)
      // prompts; there is no separate custom-catalog read.
      setCatalogPrompts(catalog.prompts);

      setCatalogFilterOptions({
        tier: catalog.filter_options.tier,
        category: catalog.filter_options.category,
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
    // IIFE so the deferred setState inside fetchMarketplace isn't read as a synchronous set.
    void (async () => { await fetchMarketplace(); })();
  }, [fetchMarketplace]);

  // Filter, ordered by name ascending
  const filteredCatalog = useMemo(() => {
    return catalogPrompts
      .filter((t) => {
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
      })
      .sort((a, b) => a.display_name.localeCompare(b.display_name));
  }, [catalogPrompts, search, categoryFilter, tierFilter]);

  const handleInstall = async (tpl: MarketplacePrompt, opts?: { force?: boolean }) => {
    const force = opts?.force ?? false;
    setInstallingId(tpl.id);
    try {
      const result = await installPrompt(tpl.id, { force });
      if (result.success) {
        toast({
          title: result.already_installed
            ? 'Already in organization'
            : isSuperAdmin
              ? `"${result.prompt_name}" installed`
              : `"${result.prompt_name}" copied to organization`,
          variant: 'success',
        });
        if (!force) {
          markInstalled(tpl.id, result, tpl.category);
        }
        onPromptsChanged();
      }
    } catch (err: unknown) {
      toast({
        title: isSuperAdmin ? 'Failed to install prompt' : 'Failed to copy prompt',
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
    let usageLine = '';
    try {
      const { workflow_count: count } = await getMarketplacePromptUsage(marketplaceId);
      usageLine = count > 0
        ? `\n\nUsed by ${count} ${count === 1 ? 'workflow' : 'workflows'}. Organization copies stay, so those workflows keep working.`
        : '';
    } catch {
      // Confirm without the count when it is unavailable
    }
    if (!(await confirm({
      title: 'Remove prompt',
      message: `Remove "${displayName}"?` + usageLine,
      confirmLabel: 'Remove',
      variant: 'danger',
    }))) return;

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
      onPromptsChanged();
    } catch (err: unknown) {
      toast({
        title: 'Failed to remove prompt',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setUninstallingId(null);
    }
  };

  const handleInstallAllByTier = async (tier: 'community' | 'plus') => {
    const notInstalled = catalogPrompts.filter(
      (t) => !installedIds.has(t.id) && t.tier === tier
    );
    if (notInstalled.length === 0) {
      toast({ title: `All ${tier} prompts already installed`, variant: 'success' });
      return;
    }
    if (
      !(await confirm({
        title: 'Install prompts',
        message: `Install ${notInstalled.length} ${tier} prompt${notInstalled.length > 1 ? 's' : ''}?`,
        confirmLabel: 'Install',
      }))
    )
      return;

    setInstallAllInProgress(tier);
    let installed = 0;
    for (const tpl of notInstalled) {
      try {
        const result = await installPrompt(tpl.id);
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
    installedIds,
    catalogFilterOptions,
    tokenConfigured,
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
    fetchMarketplace,
  };
}
