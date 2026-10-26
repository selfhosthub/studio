// ui/app/(authenticated)/dashboard/page.tsx

"use client";

import { PlusCircle, Users, Activity, HardDrive, Server, Building2, Play, Database } from "lucide-react";
import { STORAGE_KEYS, POLLING } from '@/shared/lib/constants';
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState, Suspense } from 'react';
import { getDashboardStats, DashboardStats, getSystemHealth, SystemHealthResponse } from "@/shared/api";
import { useUser } from "@/entities/user";
import { PROBE_LABELS, ProbeStatusIcon } from "../infrastructure/components/ProbeStatus";
import { plural } from '@/shared/lib/format-utils';

function DashboardContent() {
  const router = useRouter();
  const { user } = useUser();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [health, setHealth] = useState<SystemHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  // Refetch on an interval and on return to the tab, while the tab is visible.
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === 'visible') setRefreshTick((t) => t + 1);
    };
    const interval = setInterval(tick, POLLING.DEFAULT);
    document.addEventListener('visibilitychange', tick);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', tick);
    };
  }, []);

  // Handle authentication and fetch stats; a background refresh keeps the last good numbers on error
  useEffect(() => {
    // Check if localStorage is available (client-side only)
    if (typeof window !== 'undefined') {
      const storedUser = localStorage.getItem(STORAGE_KEYS.CURRENT_USER);
      if (!storedUser) {
        router.push("/login");
        return;
      }

      // org_id is now derived from the user's JWT token on the backend
      getDashboardStats()
        .then((data) => {
          setStats(data);
          setError(null);
        })
        .catch((err) => {
          if (refreshTick > 0) return;
          const errorMessage = err instanceof Error ? err.message : 'Unknown error';
          setError(`Failed to load dashboard data: ${errorMessage}`);
        })
        .finally(() => setLoading(false));
    }
  }, [router, refreshTick]);

  // Fetch system health for super_admins
  useEffect(() => {
    if (user?.role === 'super_admin') {
      getSystemHealth()
        .then((data) => {
          setHealth(data);
        })
        .catch(() => {
          // Don't set error - this is supplementary data
        });
    }
  }, [user, refreshTick]);

  return (
    <>
      <div className="page-container mt-4">
        <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <div className="spinner-md"></div>
              <p className="mt-2 text-sm text-secondary">Loading dashboard...</p>
            </div>
          </div>
        )}

        {!loading && error && (
          <div className="card bg-danger-subtle border-danger">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-danger" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-danger">Error Loading Dashboard</h3>
                <p className="mt-1 text-sm text-danger">{error}</p>
                <button
                  onClick={() => window.location.reload()}
                  className="mt-3 btn-primary text-sm"
                >
                  Refresh Page
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Org stats cards - hidden for super_admin (system org doesn't have workflows) */}
        {!loading && !error && stats && user?.role !== 'super_admin' && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <div className="stat-card stat-card-blue">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="stat-card-title">Organization Workflows</h3>
                  <p className="stat-card-value">{stats.workflows}</p>
                </div>
                <div className="stat-icon stat-icon-blue">
                  <PlusCircle className="h-6 w-6" />
                </div>
              </div>
              <div className="mt-4">
                <Link href="/workflows/list?tab=organization" className="stat-card-link">
                  View all workflows
                </Link>
              </div>
            </div>

            {stats.canViewMembers && (
              <div className="stat-card stat-card-green">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="stat-card-title">Users</h3>
                    <p className="stat-card-value">{stats.members}</p>
                  </div>
                  <div className="stat-icon stat-icon-green">
                    <Users className="h-6 w-6" />
                  </div>
                </div>
                {user?.role === 'admin' && (
                  <div className="mt-4">
                    <Link href="/organization/manage/users" className="stat-card-link">
                      Manage users
                    </Link>
                  </div>
                )}
              </div>
            )}

          </div>
        )}

        {/* Platform Stats Cards - Super Admin Only */}
        {user?.role === 'super_admin' && health?.platform && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <div className="stat-card stat-card-blue">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="stat-card-title">Organizations</h3>
                  <p className="stat-card-value">{health.platform.total_organizations}</p>
                </div>
                <div className="stat-icon stat-icon-blue">
                  <Building2 className="h-6 w-6" />
                </div>
              </div>
              <div className="mt-4">
                <Link href="/organizations/list" className="stat-card-link">
                  Manage organizations
                </Link>
              </div>
            </div>

            <div className="stat-card stat-card-green">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="stat-card-title">Logged-in Users</h3>
                  <p className="stat-card-value">{health.platform.active_users}</p>
                </div>
                <div className="stat-icon stat-icon-green">
                  <Users className="h-6 w-6" />
                </div>
              </div>
              <div className="mt-4">
                <span className="text-muted">
                  {`Last ${health.platform.active_users_window_minutes} ${plural(health.platform.active_users_window_minutes, 'minute')}`}
                </span>
              </div>
            </div>

            <div className="stat-card stat-card-purple">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="stat-card-title">Running Instances</h3>
                  <p className="stat-card-value">{health.platform.running_instances}</p>
                </div>
                <div className="stat-icon stat-icon-purple">
                  <Play className="h-6 w-6" />
                </div>
              </div>
              <div className="mt-4">
                <span className="text-muted">
                  Across all organizations
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Infrastructure Cards - Super Admin Only */}
        {user?.role === 'super_admin' && health && (
          <>
            <h2 className="section-title mt-8 mb-4">Infrastructure</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Database */}
              <Link
                href="/infrastructure?tab=database"
                className="infra-card infra-card-blue transition-all"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <Database className="w-8 h-8 text-info" />
                    <div className="ml-3">
                      <p className="infra-card-title flex items-center gap-1">
                        Database <ProbeStatusIcon status={health.database.status} />
                      </p>
                      <p className="infra-card-value">
                        {PROBE_LABELS[health.database.status]}
                      </p>
                      <p className="text-xs text-muted break-words">{health.database.message}</p>
                    </div>
                  </div>
                </div>
              </Link>

              {/* Workers */}
              <Link
                href="/infrastructure?tab=workers"
                className="infra-card infra-card-green transition-all"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <Server className="w-8 h-8 text-success" />
                    <div className="ml-3">
                      <p className="infra-card-title">Workers</p>
                      <p className="infra-card-value">
                        {health.workers.online} online
                      </p>
                    </div>
                  </div>
                  <span className="section-subtitle">
                    {health.workers.total_registered} total
                  </span>
                </div>
              </Link>

              {/* Storage */}
              <Link
                href="/infrastructure?tab=storage"
                className="infra-card infra-card-purple transition-all"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <HardDrive className="w-8 h-8 text-purple" />
                    <div className="ml-3">
                      <p className="infra-card-title">Storage</p>
                      <p className="infra-card-value">
                        {health.storage.total_size_formatted}
                      </p>
                    </div>
                  </div>
                  <span className="section-subtitle">
                    {health.storage.total_files} files
                  </span>
                </div>
              </Link>

              {/* Messaging (WebSocket) */}
              <Link
                href="/infrastructure?tab=messaging"
                className="infra-card infra-card-red transition-all"
              >
                <div className="flex items-center min-w-0">
                  <Activity className="w-8 h-8 text-danger flex-shrink-0" />
                  <div className="ml-3 min-w-0">
                    <p className="infra-card-title flex items-center gap-1">
                      Messaging <ProbeStatusIcon status={health.messaging.status} />
                    </p>
                    <p className="infra-card-value">
                      {health.websocket.total_connections}
                      <span className="text-sm font-normal text-muted whitespace-nowrap">
                        {` ${plural(health.websocket.total_connections, 'connection')} now`}
                      </span>
                    </p>
                    <p className="text-xs text-muted break-words">
                      {PROBE_LABELS[health.messaging.status]}: {health.messaging.message}
                    </p>
                  </div>
                </div>
              </Link>
            </div>
          </>
        )}
      </div>
    </>
  );
}

export default function Dashboard() {
  return (
    <Suspense fallback={
      <>
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <div className="spinner-md"></div>
            <p className="mt-2 text-sm text-secondary">Loading dashboard...</p>
          </div>
        </div>
      </>
    }>
      <DashboardContent />
    </Suspense>
  );
}
