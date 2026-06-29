// ui/app/infrastructure/components/DatabaseTabPanel.tsx

'use client';

import {
  Database,
  HardDrive,
  RefreshCw,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  Users,
  Zap,
  Gauge,
} from 'lucide-react';
import type { DatabaseStats } from '@/shared/api';

interface DatabaseTabPanelProps {
  dbStats: DatabaseStats | null;
  dbLoading: boolean;
}

export function DatabaseTabPanel({ dbStats, dbLoading }: DatabaseTabPanelProps) {
  return (
    <div className="space-y-6">
      <div className="detail-section detail-section-blue">
        <div className="detail-section-header">
          <h2 className="section-title flex items-center">
            <Database className="w-5 h-5 mr-2 text-info" />
            PostgreSQL Database
          </h2>
        </div>
        <div className="detail-section-body">
          {dbLoading && !dbStats ? (
            <div className="text-center py-8">
              <RefreshCw className="w-8 h-8 animate-spin mx-auto text-muted" />
              <p className="mt-2 text-sm text-muted">Loading database stats...</p>
            </div>
          ) : dbStats ? (
            <div className="space-y-6">
              {/* Health Status Banner */}
              <div className={`flex items-center justify-between p-4 rounded-lg border ${
                dbStats.status === 'healthy'
                  ? 'bg-success-subtle border-success'
                  : dbStats.status === 'degraded'
                  ? 'bg-warning-subtle border-warning'
                  : 'bg-danger-subtle border-danger'
              }`}>
                <div className="flex items-center gap-3">
                  {dbStats.status === 'healthy' ? (
                    <CheckCircle className="w-8 h-8 text-success" />
                  ) : dbStats.status === 'degraded' ? (
                    <AlertTriangle className="w-8 h-8 text-warning" />
                  ) : (
                    <XCircle className="w-8 h-8 text-danger" />
                  )}
                  <div>
                    <p className={`text-lg font-semibold ${
                      dbStats.status === 'healthy' ? 'text-success' :
                      dbStats.status === 'degraded' ? 'text-warning' : 'text-danger'
                    }`}>
                      {dbStats.status === 'healthy' ? 'Healthy' : dbStats.status === 'degraded' ? 'Degraded' : 'Unhealthy'}
                    </p>
                    <p className="text-sm text-muted">{dbStats.version || 'PostgreSQL'}</p>
                  </div>
                </div>
                {dbStats.uptime && (
                  <div className="text-right">
                    <div className="flex items-center gap-1 text-muted">
                      <Clock className="w-4 h-4" />
                      <span className="text-sm">Uptime</span>
                    </div>
                    <p className="text-lg font-semibold text-primary">{dbStats.uptime}</p>
                  </div>
                )}
              </div>

              {/* Key Metrics Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="p-4 bg-page rounded-lg border border-primary">
                  <div className="flex items-center gap-2 text-muted mb-1">
                    <HardDrive className="w-4 h-4" />
                    <span className="text-xs uppercase tracking-wide">Database Size</span>
                  </div>
                  <p className="text-2xl font-bold text-primary">{dbStats.database_size || '-'}</p>
                </div>

                <div className="p-4 bg-page rounded-lg border border-primary">
                  <div className="flex items-center gap-2 text-muted mb-1">
                    <Users className="w-4 h-4" />
                    <span className="text-xs uppercase tracking-wide">Connections</span>
                  </div>
                  <p className="text-2xl font-bold text-primary">
                    {dbStats.active_connections} <span className="text-sm font-normal text-muted">/ {dbStats.max_connections}</span>
                  </p>
                  {dbStats.connection_usage_percent !== null && dbStats.connection_usage_percent !== undefined && (
                    <div className="mt-2">
                      <div className="h-1.5 bg-input rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${ // css-check-ignore: no semantic token for yellow
                            dbStats.connection_usage_percent > 80 ? 'bg-danger' :
                            dbStats.connection_usage_percent > 60 ? 'bg-yellow-500' :
                            'bg-success'
                          }`}
                          style={{ width: `${Math.min(dbStats.connection_usage_percent, 100)}%` }}
                        />
                      </div>
                    </div>
                  )}
                </div>

                <div className="p-4 bg-page rounded-lg border border-primary">
                  <div className="flex items-center gap-2 text-muted mb-1">
                    <Zap className="w-4 h-4" />
                    <span className="text-xs uppercase tracking-wide">Cache Hit Ratio</span>
                  </div>
                  <p className={`text-2xl font-bold ${
                    dbStats.cache_hit_ratio !== null && dbStats.cache_hit_ratio !== undefined
                      ? dbStats.cache_hit_ratio >= 95 ? 'text-success'
                        : dbStats.cache_hit_ratio >= 90 ? 'text-warning'
                        : 'text-danger'
                      : 'text-primary'
                  }`}>
                    {dbStats.cache_hit_ratio !== null && dbStats.cache_hit_ratio !== undefined
                      ? `${dbStats.cache_hit_ratio.toFixed(1)}%` : '-'}
                  </p>
                  <p className="text-xs text-muted mt-1">
                    {dbStats.cache_hit_ratio !== null && dbStats.cache_hit_ratio !== undefined
                      ? dbStats.cache_hit_ratio >= 95 ? 'Excellent'
                        : dbStats.cache_hit_ratio >= 90 ? 'Good'
                        : 'Needs attention'
                      : 'Not available'}
                  </p>
                </div>

                <div className="p-4 bg-page rounded-lg border border-primary">
                  <div className="flex items-center gap-2 text-muted mb-1">
                    <Gauge className="w-4 h-4" />
                    <span className="text-xs uppercase tracking-wide">Slow Queries</span>
                  </div>
                  <p className={`text-2xl font-bold ${
                    dbStats.slow_queries === 0 ? 'text-success' :
                    dbStats.slow_queries <= 3 ? 'text-warning' : 'text-danger'
                  }`}>
                    {dbStats.slow_queries}
                  </p>
                  <p className="text-xs text-muted mt-1">Currently running &gt; 1s</p>
                </div>
              </div>

              {/* Record Counts */}
              <div>
                <p className="text-sm font-semibold text-primary uppercase tracking-wide mb-3">Record Counts</p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {[
                    { label: 'Organizations', value: dbStats.total_organizations },
                    { label: 'Users', value: dbStats.total_users },
                    { label: 'Workflows', value: dbStats.total_workflows },
                    { label: 'Blueprints', value: dbStats.total_blueprints },
                    { label: 'Instances', value: dbStats.total_instances },
                    { label: 'Providers', value: dbStats.total_providers },
                    { label: 'Credentials', value: dbStats.total_credentials },
                  ].map(({ label, value }) => (
                    <div key={label} className="text-center p-3 bg-page rounded-lg border border-primary">
                      <p className="text-2xl font-bold text-primary">{value.toLocaleString()}</p>
                      <p className="text-xs text-muted">{label}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-8 text-muted">
              <Database className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>Unable to load database statistics</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
