// ui/app/infrastructure/components/WorkersTabPanel.tsx

'use client';

import { Server } from 'lucide-react';
import type { SystemHealthResponse } from '@/shared/api';

// Format memory in MB to human-readable string (GB when >= 1024 MB)
function formatMemory(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb} MB`;
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
          Workers register on startup and send heartbeats every 60s
        </span>
      </div>
      <div className="detail-section-body">
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

        {health.workers.workers.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-theme">
              <thead className="bg-card">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">Worker</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-muted uppercase">Status</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">Resource Usage</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-muted uppercase">Last Heartbeat</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-muted uppercase">Jobs</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-muted uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-page divide-y divide-theme">
                {health.workers.workers.map((worker: any) => (
                  <tr key={worker.worker_id}>
                    <td className="px-4 py-2">
                      <div className="text-sm font-medium text-primary">
                        {worker.name || worker.worker_id.substring(0, 8)}
                      </div>
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
                    </td>
                    <td className="px-4 py-2 text-center">
                      <span className={worker.status === 'online' ? 'badge-success' : 'badge-default'}>
                        {worker.status}
                      </span>
                      {worker.worker_status && worker.worker_status !== 'unknown' && (
                        <span className="ml-1 text-xs text-muted">({worker.worker_status})</span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      {(worker.cpu_percent !== null || worker.memory_percent !== null) ? (
                        <div className="text-xs space-y-1">
                          {worker.cpu_percent !== null && (
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
                          {worker.memory_percent !== null && (
                            <div className="flex items-center gap-1">
                              <span className="text-muted">Mem:</span>
                              <span className={`font-medium ${
                                worker.memory_percent > 80 ? 'text-danger' :
                                worker.memory_percent > 50 ? 'text-warning' :
                                'text-success'
                              }`}>
                                {worker.memory_percent?.toFixed(1)}%
                              </span>
                              {worker.memory_used_mb && worker.memory_total_mb && (
                                <span className="text-muted">
                                  ({formatMemory(worker.memory_used_mb)} / {formatMemory(worker.memory_total_mb)})
                                </span>
                              )}
                            </div>
                          )}
                          {worker.gpu_percent !== null && (
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
                        <span className="text-xs text-muted">-</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-sm text-center text-secondary">
                      {worker.last_heartbeat_seconds_ago !== undefined
                        ? `${worker.last_heartbeat_seconds_ago}s ago`
                        : worker.last_heartbeat
                          ? new Date(worker.last_heartbeat).toLocaleTimeString()
                          : 'Never'
                      }
                    </td>
                    <td className="px-4 py-2 text-sm text-center text-secondary">
                      {worker.jobs_completed || 0}
                    </td>
                    <td className="px-4 py-2 text-center">
                      <button
                        type="button"
                        onClick={() => onDeregister(worker.worker_id, worker.name)}
                        className="link-danger text-sm"
                        title="Deregister worker"
                      >
                        Deregister
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-muted">
            <Server className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>No workers registered</p>
            <p className="mt-2 text-sm">Workers will appear here when they connect via heartbeat</p>
          </div>
        )}
      </div>
    </div>
  );
}
