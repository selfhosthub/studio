// ui/app/dashboard/page.tsx

"use client";

import { PlusCircle, Users, Activity, HardDrive, Server, CheckCircle, XCircle, Building2, Play, Database } from "lucide-react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState, Suspense } from 'react';
import { DashboardLayout } from "@/widgets/layout";
import { getDashboardStats, DashboardStats, getSystemHealth, SystemHealthResponse } from "@/shared/api";
import { useUser } from "@/entities/user";

function DashboardContent() {
  const router = useRouter();
  const { user } = useUser();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [health, setHealth] = useState<SystemHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Handle authentication and fetch stats
  useEffect(() => {
    // Check if localStorage is available (client-side only)
    if (typeof window !== 'undefined') {
      const storedUser = localStorage.getItem('workflowUser');
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
          const errorMessage = err instanceof Error ? err.message : 'Unknown error';
          setError(`Failed to load dashboard data: ${errorMessage}`);
        })
        .finally(() => setLoading(false));
    }
  }, [router]);

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
  }, [user]);

  return (
    <DashboardLayout>
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
                  className="mt-3 px-4 py-2 bg-danger text-white rounded-md hover:bg-danger focus:outline-none focus:ring-2 focus:ring-offset-2 text-sm"
                >
                  Refresh Page
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Org stats cards - hidden for super_admin (system org doesn't have workflows/blueprints) */}
        {!loading && !error && stats && user?.role !== 'super_admin' && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <div className="stat-card stat-card-blue">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="stat-card-title">Active Workflows</h3>
                  <p className="stat-card-value">{stats.workflows}</p>
                </div>
                <div className="stat-icon stat-icon-blue">
                  <PlusCircle className="h-6 w-6" />
                </div>
              </div>
              <div className="mt-4">
                <Link href="/workflows/list" className="stat-card-link">
                  View all workflows
                </Link>
              </div>
            </div>

            {stats.canViewMembers && (
              <div className="stat-card stat-card-green">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="stat-card-title">Team Members</h3>
                    <p className="stat-card-value">{stats.members}</p>
                  </div>
                  <div className="stat-icon stat-icon-green">
                    <Users className="h-6 w-6" />
                  </div>
                </div>
                {user?.org_id && user?.role === 'admin' && (
                  <div className="mt-4">
                    <Link href={`/organizations/${user.org_id}/users`} className="stat-card-link">
                      Manage team
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
                  Last 30 minutes
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
                  Across all orgs
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
                      <p className="infra-card-title">Database</p>
                      <p className="infra-card-value">
                        {health.database_connected ? 'Healthy' : 'Unhealthy'}
                      </p>
                    </div>
                  </div>
                  {health.database_connected ? (
                    <CheckCircle className="w-5 h-5 text-success" />
                  ) : (
                    <XCircle className="w-5 h-5 text-danger" />
                  )}
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
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <Activity className="w-8 h-8 text-danger" />
                    <div className="ml-3">
                      <p className="infra-card-title">Messaging</p>
                      <p className="infra-card-value">
                        {health.websocket.total_connections} connections
                      </p>
                    </div>
                  </div>
                  <CheckCircle className="w-5 h-5 text-success" />
                </div>
              </Link>
            </div>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}

export default function Dashboard() {
  return (
    <Suspense fallback={
      <DashboardLayout>
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <div className="spinner-md"></div>
            <p className="mt-2 text-sm text-secondary">Loading dashboard...</p>
          </div>
        </div>
      </DashboardLayout>
    }>
      <DashboardContent />
    </Suspense>
  );
}
