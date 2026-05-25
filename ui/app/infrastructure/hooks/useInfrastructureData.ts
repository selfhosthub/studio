// ui/app/infrastructure/hooks/useInfrastructureData.ts

'use client';

import { useState, useEffect, useCallback } from 'react';
import { PAGINATION } from '@/shared/lib/constants';
import { useSearchParams } from 'next/navigation';
import { useUser } from '@/entities/user';
import { useToast } from '@/features/toast';
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

export type TabId = 'messaging' | 'queue' | 'workers' | 'storage' | 'database';

export function useInfrastructureData() {
  const { user } = useUser();
  const { toast } = useToast();
  const searchParams = useSearchParams();

  const [health, setHealth] = useState<SystemHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshInterval, setRefreshInterval] = useState(0);

  const tabParam = searchParams.get('tab') as TabId | null;
  const resolvedTab = (tabParam as string) === 'jobs' ? 'queue' as TabId : tabParam; // ?tab=jobs was the old name for the queue tab
  const [activeTab, setActiveTab] = useState<TabId>(
    resolvedTab && ['messaging', 'queue', 'workers', 'storage', 'database'].includes(resolvedTab) ? resolvedTab : 'queue'
  );

  // Database tab state
  const [dbStats, setDbStats] = useState<DatabaseStats | null>(null);
  const [dbLoading, setDbLoading] = useState(false);

  // Storage tab state
  const [storageData, setStorageData] = useState<PaginatedStorageResponse | null>(null);
  const [storagePage, setStoragePage] = useState(1);
  const [storagePageSize, setStoragePageSize] = useState(10);
  const [storageLoading, setStorageLoading] = useState(false);
  const [storageSortBy, setStorageSortBy] = useState<StorageSortField>('size_bytes');
  const [storageSortOrder, setStorageSortOrder] = useState<SortOrder>('desc');

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
    pageSize: number = PAGINATION.DEFAULT_PAGE_SIZE,
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
    const newOrder: SortOrder = storageSortBy === field && storageSortOrder === 'desc' ? 'asc' : 'desc';
    setStorageSortBy(field);
    setStorageSortOrder(newOrder);
    fetchStorageData(1, storagePageSize, field, newOrder);
  }, [storageSortBy, storageSortOrder, storagePageSize, fetchStorageData]);

  const handleDeregisterWorker = useCallback(async (workerId: string, workerName: string) => {
    if (!confirm(`Are you sure you want to deregister worker "${workerName}"? The worker will be notified to stop gracefully.`)) {
      return;
    }
    try {
      await deregisterWorker(workerId);
      fetchHealth();
    } catch (err: unknown) {
      console.error('Failed to deregister worker:', err);
      toast({ title: 'Deregister failed', description: err instanceof Error ? err.message : 'Failed to deregister worker', variant: 'destructive' });
    }
  }, [fetchHealth, toast]);

  // Initial fetch
  useEffect(() => {
    if (isSuperAdmin) fetchHealth();
  }, [isSuperAdmin, fetchHealth]);

  // Tab-specific data fetch
  useEffect(() => {
    if (!isSuperAdmin) return;
    if (activeTab === 'database' && !dbStats && !dbLoading) {
      fetchDatabaseStats();
    } else if (activeTab === 'storage' && !storageData && !storageLoading) {
      fetchStorageData(1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- dbStats, dbLoading, storageData, storageLoading are intentionally excluded to prevent refetching when data arrives
  }, [activeTab, isSuperAdmin, fetchHealth, fetchDatabaseStats, fetchStorageData]);

  // Auto-refresh
  useEffect(() => {
    if (refreshInterval === 0 || !isSuperAdmin) return;
    const interval = setInterval(() => {
      fetchHealth();
      if (activeTab === 'database') fetchDatabaseStats();
      else if (activeTab === 'storage') fetchStorageData(storagePage, storagePageSize, storageSortBy, storageSortOrder);
    }, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval, isSuperAdmin, activeTab, storagePage, storagePageSize, storageSortBy, storageSortOrder, fetchHealth, fetchDatabaseStats, fetchStorageData]);

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
