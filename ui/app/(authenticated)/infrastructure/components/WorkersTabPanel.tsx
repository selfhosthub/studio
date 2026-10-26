// ui/app/(authenticated)/infrastructure/components/WorkersTabPanel.tsx

'use client';

import { Server } from 'lucide-react';
import type { SystemHealthResponse } from '@/shared/api';
import { ResourceTable } from '@/shared/ui';
import { formatDate, formatSecondsAgo } from '@/shared/lib/dateFormatter';
import { formatStatus } from '@/shared/lib/format-utils';

// Format memory in MB to human-readable string (GB when >= 1024 MB)
function formatMemory(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb} MB`;
}

// Time of the worker's last heartbeat, for sorting
function heartbeatTime(worker: any): number | null {
  if (worker.last_heartbeat_seconds_ago !== undefined) return Date.now() - worker.last_heartbeat_seconds_ago * 1000;
  return worker.last_heartbeat ? new Date(worker.last_heartbeat).getTime() : null;
}

// True once the worker has sent a heartbeat carrying at least one resource reading
function hasResourceSample(worker: any): boolean {
  if (heartbeatTime(worker) === null) return false;
  return worker.cpu_percent != null || worker.memory_percent != null || worker.gpu_percent != null;
}

// Worker state beside the status badge, omitted when it repeats the status
function workerStateNote(worker: any): string | null {
  const state = worker.worker_status;
  if (!state || state === 'unknown') return null;
  return String(state).toLowerCase() === String(worker.status).toLowerCase() ? null : state;
}

function formatMinutes(minutes: number): string {
  return minutes === 1 ? '1 minute' : `${minutes} minutes`;
}

interface WorkersTabPanelProps {
  health: SystemHealthResponse;
  onDeregister: (workerId: string, workerName: string) => void;
}

export function WorkersTabPanel({ health, onDeregister }: WorkersTabPanelProps) {
  return (
    <div className="detail-section detail-section-green">
      <div className="detail-section-header flex justify-between items-center">
        <h2 className="section-title flex items-center">
          <Server className="w-5 h-5 mr-2 text-success" />
          Worker Heartbeats
        </h2>
        <span className="section-subtitle">
          Workers send a heartbeat every 60s and show offline after {formatMinutes(health.workers.heartbeat_timeout_minutes)} without one
        </span>
      </div>
      <div className="detail-section-body">
        {(health.workers.unserved_queues?.length ?? 0) > 0 && (
          <div className="mb-4 bg-warning-subtle border border-warning rounded-md p-3 text-sm text-warning" role="alert">
            No workers handle: {(health.workers.unserved_queues ?? []).join(', ')}. Jobs
            on these queues will wait until a worker serves them.
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
          <div>
            <p className="infra-card-title">Total Registered</p>
            <p className="mt-1 infra-card-value">{health.workers.total_registered}</p>
          </div>
          <div>
            <p className="infra-card-title">Online</p>
            <p className="mt-1 text-lg font-semibold text-success">{health.workers.online}</p>
          </div>
          <div>
            <p className="infra-card-title">Offline</p>
            <p className="mt-1 text-lg font-semibold text-muted">{health.workers.offline}</p>
          </div>
        </div>

        <ResourceTable
          data={health.workers.workers}
          getItemId={(worker: any) => worker.worker_id}
          tieBreaker="worker"
          prefPage="infra-workers"
          pagination={{ itemLabel: 'worker' }}
          containerClassName="mb-0"
          emptyState={
            <div className="text-center py-8 text-muted">
              <Server className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>No workers registered</p>
              <p className="mt-2 text-sm">Workers will appear here when they connect via heartbeat</p>
            </div>
          }
          columns={[
            {
              key: 'worker',
              header: 'Worker',
              headerClassName: 'text-muted',
              sortValue: (worker: any) => worker.name || worker.worker_id,
              render: (worker: any) => (
                <>
                  <div className="text-sm font-medium text-primary">
                    {worker.name || worker.worker_id.substring(0, 8)}
                  </div>
                  {worker.queues?.length > 0 && (
                    <div className="text-xs text-secondary">
                      Queues: {worker.queues.join(', ')}
                    </div>
                  )}
                  {worker.queue_labels?.length > 0 && (
                    <div className="text-xs text-muted">
                      {worker.queue_labels.join(', ')}
                    </div>
                  )}
                  <div className="text-xs text-muted font-mono">{worker.worker_id}</div>
                  {(worker.ip_address || worker.hostname) && (
                    <div className="text-xs text-muted">
                      {worker.hostname && <span>{worker.hostname}</span>}
                      {worker.hostname && worker.ip_address && <span> · </span>}
                      {worker.ip_address && <span>{worker.ip_address}</span>}
                    </div>
                  )}
                  {worker.storage_mode && (
                    <div className="mt-1">
                      <span className={worker.storage_mode === 'local' ? 'badge-success' : 'badge-default'}>
                        {worker.storage_mode === 'local' ? 'local workspace' : 'remote upload'}
                      </span>
                    </div>
                  )}
                </>
              ),
            },
            {
              key: 'status',
              header: 'Status',
              align: 'center',
              headerClassName: 'text-muted',
              sortValue: (worker: any) => worker.status,
              render: (worker: any) => (
                <>
                  <span className={worker.status === 'online' ? 'badge-success' : 'badge-default'}>
                    {formatStatus(worker.status)}
                  </span>
                  {workerStateNote(worker) && (
                    <span className="ml-1 text-xs text-muted max-md:block max-md:ml-0">({workerStateNote(worker)})</span>
                  )}
                </>
              ),
            },
            {
              key: 'usage',
              header: 'Resource Usage',
              headerClassName: 'text-muted',
              sortValue: (worker: any) => worker.cpu_percent,
              render: (worker: any) => (
                <>
                  {hasResourceSample(worker) ? (
                    <div className="text-xs space-y-1">
                      {worker.cpu_percent != null && (
                        <div className="flex items-center gap-1">
                          <span className="text-muted">CPU:</span>
                          <span className={`font-medium ${
                            worker.cpu_percent > 80 ? 'text-danger' :
                            worker.cpu_percent > 50 ? 'text-warning' :
                            'text-success'
                          }`}>
                            {worker.cpu_percent?.toFixed(1)}%
                          </span>
                        </div>
                      )}
                      {worker.memory_percent != null && (
                        <div className="flex items-center gap-1">
                          <span className="text-muted">Mem:</span>
                          <span className={`font-medium ${
                            worker.memory_percent > 80 ? 'text-danger' :
                            worker.memory_percent > 50 ? 'text-warning' :
                            'text-success'
                          }`}>
                            {worker.memory_percent?.toFixed(1)}%
                          </span>
                          {worker.memory_used_mb > 0 && worker.memory_total_mb > 0 && (
                            <span className="text-muted">
                              ({formatMemory(worker.memory_used_mb)} / {formatMemory(worker.memory_total_mb)})
                            </span>
                          )}
                        </div>
                      )}
                      {worker.gpu_percent != null && (
                        <div className="flex items-center gap-1">
                          <span className="text-muted">GPU:</span>
                          <span className={`font-medium ${
                            worker.gpu_percent > 80 ? 'text-danger' :
                            worker.gpu_percent > 50 ? 'text-warning' :
                            'text-success'
                          }`}>
                            {worker.gpu_percent?.toFixed(1)}%
                          </span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <span className="text-xs text-muted">n/a</span>
                  )}
                </>
              ),
            },
            {
              key: 'heartbeat',
              header: 'Last Heartbeat',
              align: 'center',
              headerClassName: 'text-muted',
              cellClassName: 'text-secondary',
              sortValue: heartbeatTime,
              render: (worker: any) => (
                <>
                  {worker.last_heartbeat_seconds_ago !== undefined
                    ? formatSecondsAgo(worker.last_heartbeat_seconds_ago)
                    : worker.last_heartbeat
                      ? formatDate(worker.last_heartbeat)
                      : 'Never'
                  }
                </>
              ),
            },
            {
              key: 'jobs',
              header: 'Jobs',
              align: 'center',
              headerClassName: 'text-muted',
              cellClassName: 'text-secondary',
              sortValue: (worker: any) => worker.jobs_completed || 0,
              render: (worker: any) => (
                <>
                  {worker.jobs_completed || 0}
                </>
              ),
            },
            {
              key: 'actions',
              header: 'Actions',
              align: 'center',
              headerClassName: 'text-muted',
              render: (worker: any) => (
                  <button
                    type="button"
                    onClick={() => onDeregister(worker.worker_id, worker.name)}
                    className="link-danger text-sm"
                    title="Deregister worker"
                  >
                    Deregister
                  </button>
              ),
            },
          ]}
        />
      </div>
    </div>
  );
}
