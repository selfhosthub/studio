// ui/app/(authenticated)/infrastructure/page.tsx

"use client";

import { Suspense } from 'react';
import {
  Server,
  Database,
  HardDrive,
  Activity,
  RefreshCw,
  Briefcase,
} from 'lucide-react';
import { REFRESH_INTERVALS, useInfrastructureData } from './hooks/useInfrastructureData';
import { MessagingTabPanel } from './components/MessagingTabPanel';
import { QueueTabPanel } from './components/QueueTabPanel';
import { WorkersTabPanel } from './components/WorkersTabPanel';
import { WorkerEnrollmentPanel } from './components/WorkerEnrollmentPanel';
import { StorageTabPanel } from './components/StorageTabPanel';
import { DatabaseTabPanel } from './components/DatabaseTabPanel';
import { PROBE_LABELS, ProbeStatusIcon } from './components/ProbeStatus';
import { formatDate } from '@/shared/lib/dateFormatter';
import { plural } from '@/shared/lib/format-utils';

function InfrastructureContent() {
  const data = useInfrastructureData();

  if (!data.isSuperAdmin) {
    return (
      <>
        <div className="px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center">
            <h2 className="text-2xl font-bold text-primary">Access Denied</h2>
            <p className="mt-2 text-muted">Infrastructure monitoring is only available to super admins.</p>
          </div>
        </div>
      </>
    );
  }

  const jobStats = data.health?.job_stats;
  const flaggedJobs = jobStats ? jobStats.long_running_total + jobStats.jobs_without_worker_total : 0;

  return (
    <>
      <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-9xl mx-auto">
        {/* Header */}
        <div className="sm:flex sm:justify-between sm:items-center mb-8">
          <div className="mb-4 sm:mb-0">
            <h1 className="text-2xl md:text-3xl font-bold text-primary">Infrastructure</h1>
            <p className="text-sm mt-1 text-muted">System health and resource monitoring</p>
          </div>
          <div className="grid grid-flow-col sm:auto-cols-max justify-start sm:justify-end gap-2">
            <div className="flex items-center gap-2">
              <span className="section-subtitle">Auto:</span>
              <select
                value={data.refreshInterval}
                onChange={(e) => data.setRefreshInterval(Number(e.target.value))}
                className="form-select !w-auto"
              >
                {REFRESH_INTERVALS.map((interval) => (
                  <option key={interval.value} value={interval.value}>{interval.label}</option>
                ))}
              </select>
            </div>
            <button
              onClick={data.refresh}
              disabled={data.loading}
              className="btn-secondary inline-flex items-center disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${data.loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>

        {data.error && (
          <div className="mb-6 alert alert-error">
            <p className="text-sm alert-error-text">{data.error}</p>
          </div>
        )}

        {data.loading && !data.health ? (
          <div className="text-center py-12">
            <RefreshCw className="w-12 h-12 animate-spin mx-auto text-muted" />
            <p className="mt-4 text-muted">Loading system health...</p>
          </div>
        ) : data.health ? (
          <div className="space-y-6">
            {/* Quick Navigation Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
              <button
                onClick={() => data.setActiveTab('queue')}
                className={`infra-card infra-card-orange text-left transition-all ${data.activeTab === 'queue' ? 'infra-card-active' : ''}`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <Briefcase className="w-8 h-8 text-orange" />
                    <div className="ml-3">
                      <p className="infra-card-title">Queue</p>
                      <p className="infra-card-value">
                        {data.health.job_stats
                          ? `${data.health.job_stats.total_pending + data.health.job_stats.total_running} active`
                          : '0 active'}
                      </p>
                    </div>
                  </div>
                  {flaggedJobs > 0 && (
                    <span className="badge-orange">
                      {flaggedJobs}
                    </span>
                  )}
                </div>
              </button>

              <button
                onClick={() => data.setActiveTab('workers')}
                className={`infra-card infra-card-green text-left transition-all ${data.activeTab === 'workers' ? 'infra-card-active' : ''}`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <Server className="w-8 h-8 text-success" />
                    <div className="ml-3">
                      <p className="infra-card-title">Workers</p>
                      <p className="infra-card-value">{data.health.workers.online} online</p>
                    </div>
                  </div>
                  <span className="section-subtitle">{data.health.workers.total_registered} total</span>
                </div>
              </button>

              <button
                onClick={() => data.setActiveTab('storage')}
                className={`infra-card infra-card-purple text-left transition-all ${data.activeTab === 'storage' ? 'infra-card-active' : ''}`}
              >
                <div className="flex items-center min-w-0">
                  <HardDrive className="w-8 h-8 text-purple flex-shrink-0" />
                  <div className="ml-3 min-w-0">
                    <p className="infra-card-title">Storage</p>
                    <p className="infra-card-value whitespace-nowrap">{data.health.storage.total_size_formatted}</p>
                    <p className="text-xs text-muted flex flex-wrap gap-x-1">
                      {data.health.storage.capacity_formatted && (
                        <span className="whitespace-nowrap">of {data.health.storage.capacity_formatted} ·</span>
                      )}
                      <span className="whitespace-nowrap">{data.health.storage.total_files.toLocaleString()} files</span>
                    </p>
                  </div>
                </div>
              </button>

              <button
                onClick={() => data.setActiveTab('database')}
                className={`infra-card infra-card-blue text-left transition-all ${data.activeTab === 'database' ? 'infra-card-active' : ''}`}
              >
                <div className="flex items-center min-w-0">
                  <Database className="w-8 h-8 text-info flex-shrink-0" />
                  <div className="ml-3 min-w-0">
                    <p className="infra-card-title flex items-center gap-1">
                      Database <ProbeStatusIcon status={data.health.database.status} />
                    </p>
                    <p className="infra-card-value">{PROBE_LABELS[data.health.database.status]}</p>
                    <p className="text-xs text-muted break-words">{data.health.database.message}</p>
                  </div>
                </div>
              </button>

              <button
                onClick={() => data.setActiveTab('messaging')}
                className={`infra-card infra-card-red text-left transition-all ${data.activeTab === 'messaging' ? 'infra-card-active' : ''}`}
              >
                <div className="flex items-center min-w-0">
                  <Activity className="w-8 h-8 text-danger flex-shrink-0" />
                  <div className="ml-3 min-w-0">
                    <p className="infra-card-title flex items-center gap-1">
                      Messaging <ProbeStatusIcon status={data.health.messaging.status} />
                    </p>
                    <p className="infra-card-value">
                      {data.health.websocket?.total_connections ?? 0}
                      <span className="text-sm font-normal text-muted whitespace-nowrap">
                        {` ${plural(data.health.websocket?.total_connections ?? 0, 'connection')} now`}
                      </span>
                    </p>
                    <p className="text-xs text-muted break-words">
                      {PROBE_LABELS[data.health.messaging.status]}: {data.health.messaging.message}
                    </p>
                  </div>
                </div>
              </button>
            </div>

            {/* Tabs Navigation */}
            <div className="border-b border-primary">
              <nav className="-mb-px flex flex-wrap gap-x-6">
                <button
                  onClick={() => data.setActiveTab('queue')}
                  className={`flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                    data.activeTab === 'queue'
                      ? 'border-orange text-orange'
                      : 'border-transparent text-muted hover:text-primary hover:border-primary'
                  }`}
                >
                  <Briefcase className="w-4 h-4" />
                  Queue
                  {flaggedJobs > 0 && (
                    <span className="ml-1 badge-orange">
                      {flaggedJobs}
                    </span>
                  )}
                </button>
                <button
                  onClick={() => data.setActiveTab('workers')}
                  className={`flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                    data.activeTab === 'workers'
                      ? 'border-success text-success'
                      : 'border-transparent text-muted hover:text-primary hover:border-primary'
                  }`}
                >
                  <Server className="w-4 h-4" />
                  Workers
                  {data.health.workers.offline > 0 && (
                    <span className="ml-1 px-1.5 py-0.5 text-xs font-medium rounded-full bg-danger-subtle text-danger">
                      {data.health.workers.offline} offline
                    </span>
                  )}
                </button>
                <button
                  onClick={() => data.setActiveTab('storage')}
                  className={`flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                    data.activeTab === 'storage'
                      ? 'border-purple text-purple'
                      : 'border-transparent text-muted hover:text-primary hover:border-primary'
                  }`}
                >
                  <HardDrive className="w-4 h-4" />
                  Storage
                </button>
                <button
                  onClick={() => data.setActiveTab('database')}
                  className={`flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                    data.activeTab === 'database'
                      ? 'border-info text-info'
                      : 'border-transparent text-muted hover:text-primary hover:border-primary'
                  }`}
                >
                  <Database className="w-4 h-4" />
                  Database
                </button>
                <button
                  onClick={() => data.setActiveTab('messaging')}
                  className={`flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                    data.activeTab === 'messaging'
                      ? 'border-danger text-danger'
                      : 'border-transparent text-muted hover:text-primary hover:border-primary'
                  }`}
                >
                  <Activity className="w-4 h-4" />
                  Messaging
                </button>
              </nav>
            </div>

            {/* Tab Content */}
            <div className="mt-6">
              {data.activeTab === 'messaging' && <MessagingTabPanel health={data.health} />}
              {data.activeTab === 'queue' && <QueueTabPanel health={data.health} />}
              {data.activeTab === 'workers' && (
                <>
                  <WorkersTabPanel health={data.health} onDeregister={data.handleDeregisterWorker} />
                  <WorkerEnrollmentPanel refreshSignal={data.health} />
                </>
              )}
              {data.activeTab === 'storage' && (
                <StorageTabPanel
                  health={data.health}
                  storageData={data.storageData}
                  storagePage={data.storagePage}
                  storagePageSize={data.storagePageSize}
                  storageLoading={data.storageLoading}
                  storageSortBy={data.storageSortBy}
                  storageSortOrder={data.storageSortOrder}
                  onSort={data.handleStorageSort}
                  onPageChange={(p, ps) => data.fetchStorageData(p, ps, data.storageSortBy, data.storageSortOrder)}
                  onPageSizeChange={(size) => {
                    data.setStoragePageSize(size);
                    data.fetchStorageData(1, size, data.storageSortBy, data.storageSortOrder);
                  }}
                  onRefresh={() => data.fetchStorageData(data.storagePage, data.storagePageSize, data.storageSortBy, data.storageSortOrder)}
                />
              )}
              {data.activeTab === 'database' && (
                <DatabaseTabPanel dbStats={data.dbStats} dbLoading={data.dbLoading} />
              )}
            </div>

            {/* Last Updated */}
            <div className="text-center text-sm text-muted">
              Last updated: {formatDate(data.health.timestamp)}
            </div>
          </div>
        ) : null}
      </div>
    </>
  );
}

export default function InfrastructurePage() {
  return (
    <Suspense fallback={<><div className="p-8 text-center text-muted">Loading...</div></>}>
      <InfrastructureContent />
    </Suspense>
  );
}
