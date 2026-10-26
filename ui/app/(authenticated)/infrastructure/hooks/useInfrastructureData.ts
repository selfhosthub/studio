// ui/app/(authenticated)/infrastructure/hooks/useInfrastructureData.ts

'use client';

import { useState, useEffect, useCallback } from 'react';
import { DEFAULT_PAGE_SIZE } from '@/shared/lib/pagination';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { isPageSize, oneOf, useListPref, type ListPrefGuard } from '@/shared/hooks/useListPref';
import { useUser } from '@/entities/user';
import { useToast } from '@/features/toast';
import { useConfirm } from '@/shared/ui/ConfirmDialog';
import {
  getSystemHealth,
  deregisterWorker,
  getDatabaseStats,
  getOrganizationStorage,
  type SystemHealthResponse,
  type DatabaseStats,
  type PaginatedStorageResponse,
  type StorageSortField,
  type SortOrder,
} from '@/shared/api';

export const TAB_IDS = ['queue', 'workers', 'storage', 'database', 'messaging'] as const;
export type TabId = (typeof TAB_IDS)[number];

const DEFAULT_TAB: TabId = 'queue';

export const REFRESH_INTERVALS = [
  { label: 'Off', value: 0 },
  { label: '5s', value: 5000 },
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
  { label: '5m', value: 300000 },
];

const isRefreshInterval: ListPrefGuard<number> = (value): value is number =>
  REFRESH_INTERVALS.some((interval) => interval.value === value);
const isStorageSortField = oneOf<StorageSortField>(['name', 'files', 'size_bytes', 'usage_percent']);
const isSortOrder = oneOf<SortOrder>(['asc', 'desc']);
const isTabId = oneOf(TAB_IDS);

// Maps a ?tab= value to a tab; jobs is the old name for the queue tab
function tabFromParam(param: string | null): TabId | null {
  if (param === 'jobs') return 'queue';
  return isTabId(param) ? param : null;
}

export function useInfrastructureData() {
  const { user } = useUser();
  const { toast } = useToast();
  const confirm = useConfirm();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const [health, setHealth] = useState<SystemHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshInterval, setRefreshInterval] = useListPref('infrastructure', 'refreshInterval', 0, isRefreshInterval);

  const tabParam = searchParams.get('tab');
  const urlTab = tabFromParam(tabParam);
  const [storedTab, setStoredTab] = useListPref('infrastructure', 'tab', DEFAULT_TAB, isTabId);
  const [activeTab, setActiveTabState] = useState<TabId>(urlTab ?? storedTab);

  const replaceTabInUrl = useCallback((tab: TabId) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set('tab', tab);
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }, [searchParams, pathname, router]);

  // Follows the URL when it names a different tab, as on back and forward
  const [seenTabParam, setSeenTabParam] = useState(tabParam);
  if (tabParam !== seenTabParam) {
    setSeenTabParam(tabParam);
    if (urlTab) setActiveTabState(urlTab);
  }

  // Writes the shown tab into a URL that names none, or names it by an old or unknown value
  useEffect(() => {
    if (tabParam !== urlTab || !urlTab) replaceTabInUrl(activeTab);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs only when the URL changes, never on a tab click
  }, [tabParam]);

  useEffect(() => {
    setStoredTab(activeTab);
  }, [activeTab, setStoredTab]);

  const setActiveTab = useCallback((tab: TabId) => {
    setActiveTabState(tab);
    replaceTabInUrl(tab);
  }, [replaceTabInUrl]);

  // Database tab state
  const [dbStats, setDbStats] = useState<DatabaseStats | null>(null);
  const [dbLoading, setDbLoading] = useState(false);

  // Storage tab state
  const [storageData, setStorageData] = useState<PaginatedStorageResponse | null>(null);
  const [storagePage, setStoragePage] = useState(1);
  const [storagePageSize, setStoragePageSize] = useListPref('infra-storage', 'pageSize', DEFAULT_PAGE_SIZE, isPageSize);
  const [storageLoading, setStorageLoading] = useState(false);
  const [storageSortBy, setStorageSortBy] = useListPref<StorageSortField>('infra-storage', 'sortBy', 'size_bytes', isStorageSortField);
  const [storageSortOrder, setStorageSortOrder] = useListPref<SortOrder>('infra-storage', 'sortOrder', 'desc', isSortOrder);

  const isSuperAdmin = user?.role === 'super_admin';

  const fetchHealth = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getSystemHealth();
      setHealth(data);
    } catch (err: unknown) {
      console.error('Failed to fetch system health:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch system health');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchDatabaseStats = useCallback(async () => {
    try {
      setDbLoading(true);
      const data = await getDatabaseStats();
      setDbStats(data);
    } catch (err: unknown) {
      console.error('Failed to fetch database stats:', err);
    } finally {
      setDbLoading(false);
    }
  }, []);

  const fetchStorageData = useCallback(async (
    page: number = 1,
    pageSize: number = DEFAULT_PAGE_SIZE,
    sortBy: StorageSortField = 'size_bytes',
    sortOrder: SortOrder = 'desc'
  ) => {
    try {
      setStorageLoading(true);
      const data = await getOrganizationStorage(page, pageSize, sortBy, sortOrder);
      setStorageData(data);
      setStoragePage(page);
    } catch (err: unknown) {
      console.error('Failed to fetch storage data:', err);
    } finally {
      setStorageLoading(false);
    }
  }, []);

  const handleStorageSort = useCallback((field: StorageSortField) => {
    const newOrder: SortOrder = storageSortBy === field && storageSortOrder === 'asc' ? 'desc' : 'asc';
    setStorageSortBy(field);
    setStorageSortOrder(newOrder);
    fetchStorageData(1, storagePageSize, field, newOrder);
  }, [storageSortBy, storageSortOrder, storagePageSize, fetchStorageData, setStorageSortBy, setStorageSortOrder]);

  const handleDeregisterWorker = useCallback(async (workerId: string, workerName: string) => {
    if (!(await confirm({
      title: 'Deregister worker',
      message: `Are you sure you want to deregister worker "${workerName}"? The worker will be notified to stop gracefully.`,
      confirmLabel: 'Deregister',
      variant: 'danger',
    }))) {
      return;
    }
    try {
      await deregisterWorker(workerId);
      fetchHealth();
    } catch (err: unknown) {
      console.error('Failed to deregister worker:', err);
      toast({ title: 'Deregister failed', description: err instanceof Error ? err.message : 'Failed to deregister worker', variant: 'destructive' });
    }
  }, [confirm, fetchHealth, toast]);

  // Initial fetch
  useEffect(() => {
    if (isSuperAdmin) void (async () => { await fetchHealth(); })();
  }, [isSuperAdmin, fetchHealth]);

  // Tab-specific data fetch
  useEffect(() => {
    if (!isSuperAdmin) return;
    if (activeTab === 'database' && !dbStats && !dbLoading) {
      void (async () => { await fetchDatabaseStats(); })();
    } else if (activeTab === 'storage' && !storageData && !storageLoading) {
      void (async () => { await fetchStorageData(1, storagePageSize, storageSortBy, storageSortOrder); })();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- dbStats, dbLoading, storageData, storageLoading are intentionally excluded to prevent refetching when data arrives
  }, [activeTab, isSuperAdmin, fetchHealth, fetchDatabaseStats, fetchStorageData]);

  // Reloads the health snapshot and the data of the open panel
  const refresh = useCallback(() => {
    fetchHealth();
    if (activeTab === 'database') fetchDatabaseStats();
    else if (activeTab === 'storage') fetchStorageData(storagePage, storagePageSize, storageSortBy, storageSortOrder);
  }, [activeTab, storagePage, storagePageSize, storageSortBy, storageSortOrder, fetchHealth, fetchDatabaseStats, fetchStorageData]);

  // Auto-refresh
  useEffect(() => {
    if (refreshInterval === 0 || !isSuperAdmin) return;
    const interval = setInterval(refresh, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval, isSuperAdmin, refresh]);

  return {
    health,
    loading,
    error,
    refreshInterval,
    setRefreshInterval,
    activeTab,
    setActiveTab,
    isSuperAdmin,
    fetchHealth,
    refresh,

    // Database
    dbStats,
    dbLoading,

    // Storage
    storageData,
    storagePage,
    storagePageSize,
    setStoragePageSize,
    storageLoading,
    storageSortBy,
    storageSortOrder,
    fetchStorageData,
    handleStorageSort,

    // Workers
    handleDeregisterWorker,
  };
}
