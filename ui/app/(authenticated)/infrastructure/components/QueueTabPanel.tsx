// ui/app/(authenticated)/infrastructure/components/QueueTabPanel.tsx

'use client';

import {
  CheckCircle,
  AlertTriangle,
  HelpCircle,
} from 'lucide-react';
import type { JobStats, SystemHealthResponse } from '@/shared/api';
import { ResourceTable, type ResourceColumnConfig } from '@/shared/ui';
import { formatDate } from '@/shared/lib/dateFormatter';

type WorkflowRow = { workflow: string } & JobStats['by_workflow'][string];
type LongRunningRow = JobStats['long_running_jobs'][number] & { id: string };
type StalledRow = JobStats['jobs_without_worker'][number] & { id: string };

/** Compacts a Jobs by Workflow cell below md and lets its sort icon wrap under the label. */
const COMPACT_CELL = 'max-md:px-2! max-md:[&>button]:flex-wrap';

/** Shows a short header label below md, keeping the full word as the accessible name. */
function shortHeader(full: string, short: string) {
  return (
    <span title={full}>
      <span aria-hidden="true" className="md:hidden">{short}</span>
      <span className="max-md:sr-only">{full}</span>
    </span>
  );
}

const workflowColumns: ResourceColumnConfig<WorkflowRow>[] = [
  { key: 'workflow', header: shortHeader('Workflow', 'Name'), headerClassName: `text-secondary ${COMPACT_CELL}`, cellClassName: `text-primary ${COMPACT_CELL}`, sortValue: (r) => r.workflow, render: (r) => r.workflow },
  { key: 'pending', header: shortHeader('Pending', 'Pend'), align: 'right', headerClassName: `text-warning ${COMPACT_CELL}`, cellClassName: `text-warning ${COMPACT_CELL}`, sortValue: (r) => r.pending, render: (r) => r.pending },
  { key: 'running', header: shortHeader('Running', 'Run'), align: 'right', headerClassName: `text-info ${COMPACT_CELL}`, cellClassName: `text-info ${COMPACT_CELL}`, sortValue: (r) => r.running, render: (r) => r.running },
  { key: 'completed', header: shortHeader('Completed', 'Done'), align: 'right', headerClassName: `text-success ${COMPACT_CELL}`, cellClassName: `text-success ${COMPACT_CELL}`, sortValue: (r) => r.completed, render: (r) => r.completed },
  { key: 'failed', header: shortHeader('Failed', 'Fail'), align: 'right', headerClassName: `text-danger ${COMPACT_CELL}`, cellClassName: `text-danger ${COMPACT_CELL}`, sortValue: (r) => r.failed, render: (r) => r.failed },
];


function jobColumns<T extends LongRunningRow | StalledRow>(headerClassName: string): ResourceColumnConfig<T>[] {
  return [
    { key: 'organization', header: 'Organization', headerClassName, cellClassName: 'text-primary', sortValue: (j) => j.organization_name, render: (j) => j.organization_name },
    { key: 'instance', header: 'Instance', headerClassName, cellClassName: 'text-primary', sortValue: (j) => j.instance_name, render: (j) => j.instance_name },
    { key: 'step', header: 'Node', headerClassName, cellClassName: 'text-secondary', sortValue: (j) => j.step_id, render: (j) => j.step_id },
  ];
}

/** Gives each job row an id that stays unique when two rows share an instance and step. */
function withIds<T extends { instance_id: string; step_id: string }>(jobs: T[]): (T & { id: string })[] {
  return jobs.map((job, index) => ({ ...job, id: `${job.instance_id}-${job.step_id}-${index}` }));
}

// "20 of 57" when the API capped the list, otherwise the count
export function shownOfTotal(shown: number, total: number): string {
  return total > shown ? `${shown} of ${total}` : `${shown}`;
}

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

  const workflowRows: WorkflowRow[] = Object.entries(jobStats.by_workflow).map(([workflow, stats]) => ({ workflow, ...stats }));
  const longRunningRows = withIds(jobStats.long_running_jobs);
  const stalledRows = withIds(jobStats.jobs_without_worker);
  const longRunningHeader = `text-secondary ${jobStats.long_running_jobs.length > 0 ? 'bg-warning-subtle' : ''}`;
  const stalledHeader = `text-secondary ${jobStats.jobs_without_worker.length > 0 ? 'bg-warning-subtle' : ''}`;
  const longRunningColumns: ResourceColumnConfig<LongRunningRow>[] = [
    ...jobColumns<LongRunningRow>(longRunningHeader),
    { key: 'running', header: 'Running', align: 'right', headerClassName: longRunningHeader, cellClassName: 'text-warning font-medium', sortValue: (j) => j.running_minutes, render: (j) => `${j.running_minutes} min` },
  ];
  const stalledColumns: ResourceColumnConfig<StalledRow>[] = [
    ...jobColumns<StalledRow>(stalledHeader),
    {
      key: 'created',
      header: 'Created',
      headerClassName: stalledHeader,
      cellClassName: 'text-secondary whitespace-nowrap',
      sortValue: (j) => (j.enqueued_at ? new Date(j.enqueued_at) : null),
      render: (j) => (j.enqueued_at ? formatDate(j.enqueued_at) : '-'),
    },
  ];

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
          <ResourceTable
            data={workflowRows}
            getItemId={(row) => row.workflow}
            tieBreaker="workflow"
            columns={workflowColumns}
            prefPage="infra-jobs-by-workflow"
            pagination={{ itemLabel: 'workflow' }}
            emptyMessage="No workflow jobs found"
            containerClassName="mb-0"
          />
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
            <span className="text-sm text-muted">({shownOfTotal(jobStats.long_running_jobs.length, jobStats.long_running_total)})</span>
          </div>
        </div>
        <div className="detail-section-body">
          <ResourceTable
            data={longRunningRows}
            getItemId={(row) => row.id}
            tieBreaker="instance"
            nameColumn="instance"
            columns={longRunningColumns}
            prefPage="infra-long-running"
            pagination={{ itemLabel: 'job' }}
            emptyMessage="No long-running jobs"
            containerClassName={`mb-0 ${jobStats.long_running_jobs.length > 0 ? 'border-warning' : 'border-primary'}`}
          />
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
            <span className="text-sm text-muted">({shownOfTotal(jobStats.jobs_without_worker.length, jobStats.jobs_without_worker_total)})</span>
          </div>
        </div>
        <div className="detail-section-body">
          <ResourceTable
            data={stalledRows}
            getItemId={(row) => row.id}
            tieBreaker="instance"
            nameColumn="instance"
            columns={stalledColumns}
            prefPage="infra-stalled"
            pagination={{ itemLabel: 'job' }}
            emptyMessage="No stalled jobs"
            containerClassName={`mb-0 ${jobStats.jobs_without_worker.length > 0 ? 'border-warning' : 'border-primary'}`}
          />
        </div>
      </div>
    </div>
  );
}
