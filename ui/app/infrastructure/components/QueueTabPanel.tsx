// ui/app/infrastructure/components/QueueTabPanel.tsx

'use client';

import Link from 'next/link';
import {
  CheckCircle,
  AlertTriangle,
  HelpCircle,
} from 'lucide-react';
import type { SystemHealthResponse } from '@/shared/api';

interface QueueTabPanelProps {
  health: SystemHealthResponse;
}

export function QueueTabPanel({ health }: QueueTabPanelProps) {
  const jobStats = health.job_stats;

  if (!jobStats) {
    return (
      <div className="text-center py-8 text-muted">No job statistics available</div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Job Statistics */}
      <div className="detail-section detail-section-orange">
        <div className="detail-section-header">
          <div className="flex items-center gap-2">
            <h2 className="section-title">Job Statistics</h2>
            <div className="group relative">
              <HelpCircle className="w-4 h-4 text-muted cursor-help" />
              <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block w-80 p-3 bg-gray-900 text-white text-xs rounded shadow-lg z-10"> {/* css-check-ignore */}
                <div className="space-y-2">
                  <div><span className="text-yellow-400 font-medium">Pending:</span> Jobs waiting in queue to be picked up by a worker</div> {/* css-check-ignore */}
                  <div><span className="text-blue-400 font-medium">Running:</span> Jobs currently being processed by a worker</div> {/* css-check-ignore */}
                  <div><span className="text-green-400 font-medium">Completed:</span> Jobs that finished successfully</div> {/* css-check-ignore */}
                  <div><span className="text-red-400 font-medium">Failed:</span> Jobs that encountered errors during execution</div> {/* css-check-ignore */}
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="detail-section-body">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center p-3 bg-page rounded-lg border border-primary">
              <p className="text-2xl font-bold text-warning">{jobStats.total_pending}</p>
              <p className="text-xs text-muted">Pending</p>
            </div>
            <div className="text-center p-3 bg-page rounded-lg border border-primary">
              <p className="text-2xl font-bold text-info">{jobStats.total_running}</p>
              <p className="text-xs text-muted">Running</p>
            </div>
            <div className="text-center p-3 bg-page rounded-lg border border-primary">
              <p className="text-2xl font-bold text-success">{jobStats.total_completed}</p>
              <p className="text-xs text-muted">Completed</p>
            </div>
            <div className="text-center p-3 bg-page rounded-lg border border-primary">
              <p className="text-2xl font-bold text-danger">{jobStats.total_failed}</p>
              <p className="text-xs text-muted">Failed</p>
            </div>
          </div>
        </div>
      </div>

      {/* Jobs by Workflow */}
      <div className="detail-section detail-section-orange">
        <div className="detail-section-header">
          <h2 className="section-title">Jobs by Workflow</h2>
        </div>
        <div className="detail-section-body">
          <div className="overflow-x-auto rounded-lg border border-primary">
            <table className="min-w-full divide-y divide-theme">
              <thead>
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-secondary uppercase">Workflow</th>
                  <th className="px-4 py-2.5 text-right text-xs font-semibold text-warning uppercase">Pending</th>
                  <th className="px-4 py-2.5 text-right text-xs font-semibold text-info uppercase">Running</th>
                  <th className="px-4 py-2.5 text-right text-xs font-semibold text-success uppercase">Completed</th>
                  <th className="px-4 py-2.5 text-right text-xs font-semibold text-danger uppercase">Failed</th>
                </tr>
              </thead>
              <tbody className="bg-page divide-y divide-theme">
                {Object.keys(jobStats.by_workflow).length > 0 ? (
                  Object.entries(jobStats.by_workflow).map(([workflow, stats]) => (
                    <tr key={workflow}>
                      <td className="px-4 py-2 text-sm text-primary">{workflow}</td>
                      <td className="px-4 py-2 text-sm text-right text-warning">{stats.pending}</td>
                      <td className="px-4 py-2 text-sm text-right text-info">{stats.running}</td>
                      <td className="px-4 py-2 text-sm text-right text-success">{stats.completed}</td>
                      <td className="px-4 py-2 text-sm text-right text-danger">{stats.failed}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="px-4 py-4 text-sm text-center text-muted">No workflow jobs found</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Long Running Jobs */}
      <div className={`detail-section detail-section-orange ${jobStats.long_running_jobs.length > 0 ? 'border-warning/50' : ''}`}>
        <div className={`detail-section-header ${jobStats.long_running_jobs.length > 0 ? 'bg-warning-subtle' : ''}`}>
          <div className="flex items-center gap-2">
            {jobStats.long_running_jobs.length > 0 ? (
              <AlertTriangle className="w-5 h-5 text-warning" />
            ) : (
              <CheckCircle className="w-5 h-5 text-success" />
            )}
            <h2 className={`section-title ${jobStats.long_running_jobs.length > 0 ? 'text-warning' : ''}`}>
              Long Running Jobs (&gt;30 min)
            </h2>
            <span className="text-sm text-muted">({jobStats.long_running_jobs.length})</span>
          </div>
        </div>
        <div className="detail-section-body">
          <div className={`overflow-x-auto rounded-lg border ${jobStats.long_running_jobs.length > 0 ? 'border-warning' : 'border-primary'}`}>
            <table className="min-w-full divide-y divide-theme">
              <thead className={jobStats.long_running_jobs.length > 0 ? 'bg-warning-subtle' : ''}>
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-secondary uppercase">Organization</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-secondary uppercase">Instance</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-secondary uppercase">Step</th>
                  <th className="px-4 py-2.5 text-right text-xs font-semibold text-secondary uppercase">Running</th>
                </tr>
              </thead>
              <tbody className="bg-page divide-y divide-theme">
                {jobStats.long_running_jobs.length > 0 ? (
                  jobStats.long_running_jobs.map((job, index) => (
                    <tr key={`${job.instance_id}-${job.step_id}-${index}`}>
                      <td className="px-4 py-2 text-sm text-primary">{job.organization_name}</td>
                      <td className="px-4 py-2 text-sm">
                        <Link href={`/instances/${job.instance_id}`} className="link">{job.instance_name}</Link>
                      </td>
                      <td className="px-4 py-2 text-sm text-secondary">{job.step_id}</td>
                      <td className="px-4 py-2 text-sm text-right text-warning font-medium">{job.running_minutes} min</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="px-4 py-4 text-sm text-center text-muted">No long-running jobs</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Stalled Jobs */}
      <div className={`detail-section detail-section-orange ${jobStats.jobs_without_worker.length > 0 ? 'border-warning/50' : ''}`}>
        <div className={`detail-section-header ${jobStats.jobs_without_worker.length > 0 ? 'bg-warning-subtle' : ''}`}>
          <div className="flex items-center gap-2">
            {jobStats.jobs_without_worker.length > 0 ? (
              <AlertTriangle className="w-5 h-5 text-warning" />
            ) : (
              <CheckCircle className="w-5 h-5 text-success" />
            )}
            <h2 className={`section-title ${jobStats.jobs_without_worker.length > 0 ? 'text-warning' : ''}`}>
              Stalled Jobs (Pending &gt;5 min)
            </h2>
            <span className="text-sm text-muted">({jobStats.jobs_without_worker.length})</span>
          </div>
        </div>
        <div className="detail-section-body">
          <div className={`overflow-x-auto rounded-lg border ${jobStats.jobs_without_worker.length > 0 ? 'border-warning' : 'border-primary'}`}>
            <table className="min-w-full divide-y divide-theme">
              <thead className={jobStats.jobs_without_worker.length > 0 ? 'bg-warning-subtle' : ''}>
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-secondary uppercase">Organization</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-secondary uppercase">Instance</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-secondary uppercase">Step</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-secondary uppercase">Created</th>
                </tr>
              </thead>
              <tbody className="bg-page divide-y divide-theme">
                {jobStats.jobs_without_worker.length > 0 ? (
                  jobStats.jobs_without_worker.map((job, index) => (
                    <tr key={`${job.instance_id}-${job.step_id}-${index}`}>
                      <td className="px-4 py-2 text-sm text-primary">{job.organization_name}</td>
                      <td className="px-4 py-2 text-sm">
                        <Link href={`/instances/${job.instance_id}`} className="link">{job.instance_name}</Link>
                      </td>
                      <td className="px-4 py-2 text-sm text-secondary">{job.step_id}</td>
                      <td className="px-4 py-2 text-sm text-secondary whitespace-nowrap">
                        {job.enqueued_at ? new Date(job.enqueued_at).toLocaleString([], {dateStyle: 'short', timeStyle: 'short'}) : '-'}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="px-4 py-4 text-sm text-center text-muted">No stalled jobs</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
