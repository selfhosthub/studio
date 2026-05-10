// ui/app/instances/[id]/step_executions/page.tsx

'use client';

import { DashboardLayout } from '@/widgets/layout';
import { useUser } from '@/entities/user';
import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { formatDate } from '@/shared/lib/dateFormatter';
import { getJobsForInstance, getInstance } from '@/shared/api';
import { useToast } from '@/features/toast';
import {
  Table, TableHeader, TableBody, TableRow, TableCell,
  TableHeaderCell, StatusBadge, ActionButton, TableContainer
} from '@/shared/ui/Table';

interface Job {
  id: string;
  workflow_instance_id?: string;
  instance_id?: string;
  instance_step_id?: string | null;
  step_id: string;
  step_name?: string;
  status: string;
  result: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  retry_count?: number;
  execution_data?: Record<string, unknown>;
  input_data?: Record<string, unknown>;
  request_body?: Record<string, unknown> | null;
  iteration_requests?: Record<string, unknown>[] | null;
  created_at: string | null;
  updated_at: string | null;
  duration?: string;
}

// Helper function to calculate duration
const calculateDuration = (startedAt: string | null, completedAt: string | null): string => {
  if (!startedAt) return "N/A";

  const start = new Date(startedAt);
  const end = completedAt ? new Date(completedAt) : new Date();
  const durationMs = end.getTime() - start.getTime();

  const minutes = Math.floor(durationMs / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${minutes % 60}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${Math.floor(durationMs / 1000)}s`;
};

export default function InstanceJobMonitoring() {
  const params = useParams();
  const router = useRouter();
  const instanceId = params?.id as string;
  const { user, status } = useUser();
  const { toast } = useToast();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [instanceName, setInstanceName] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchJobs = useCallback(async () => {
    if (!instanceId) return;

    try {
      setIsLoading(true);
      setError(null);

      // Fetch instance to get name/metadata
      const instance = await getInstance(instanceId);
      setInstanceName(instance.client_metadata?.name || `Instance ${instanceId.slice(0, 8)}`);

      // Fetch jobs for this instance
      const fetchedJobs = await getJobsForInstance(instanceId);

      // Add duration to each job
      const jobsWithDuration = fetchedJobs.map((job) => ({
        ...job,
        duration: calculateDuration(job.started_at, job.completed_at),
      }));

      setJobs(jobsWithDuration);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load jobs');
    } finally {
      setIsLoading(false);
    }
  }, [instanceId]);

  useEffect(() => {
    fetchJobs();
  }, [instanceId, fetchJobs]);

  return (
    <DashboardLayout>
      <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-9xl mx-auto">
        <div className="sm:flex sm:justify-between sm:items-center mb-8">
          <div className="mb-4 sm:mb-0">
            <h1 className="text-2xl md:text-3xl font-bold text-primary">
              Job Monitoring
            </h1>
            <p className="text-sm text-secondary mt-1">
              Monitor jobs for {instanceName}
            </p>
          </div>
          <div className="flex gap-2">
            <button
              className="btn bg-surface text-primary hover:bg-input"
              onClick={() => router.push(`/instances/${instanceId}`)}
            >
              <svg className="w-4 h-4 fill-current" viewBox="0 0 16 16">
                <path d="M9.5 13a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0zm0-5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0zm0-5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
              </svg>
              <span className="hidden xs:block ml-2">Back to Instance</span>
            </button>
            <button
              className="btn btn-primary"
              onClick={fetchJobs}
            >
              <svg className="w-4 h-4 fill-current opacity-50 shrink-0" viewBox="0 0 16 16">
                <path d="M11.534 7h3.932a.25.25 0 0 1 .192.41l-1.966 2.36a.25.25 0 0 1-.384 0l-1.966-2.36a.25.25 0 0 1 .192-.41zm-11 2h3.932a.25.25 0 0 0 .192-.41L2.692 6.23a.25.25 0 0 0-.384 0L.342 8.59A.25.25 0 0 0 .534 9z"/>
                <path fillRule="evenodd" d="M8 3c-1.552 0-2.94.707-3.857 1.818a.5.5 0 1 1-.771-.636A6.002 6.002 0 0 1 13.917 7H12.9A5.002 5.002 0 0 0 8 3zM3.1 9a5.002 5.002 0 0 0 8.757 2.182.5.5 0 1 1 .771.636A6.002 6.002 0 0 1 2.083 9H3.1z"/>
              </svg>
              <span className="hidden xs:block ml-2">Refresh</span>
            </button>
          </div>
        </div>

        {error ? (
          <div className="alert alert-error">
            <p className="text-danger">{error}</p>
          </div>
        ) : isLoading ? (
          <div className="text-center py-10">
            <div className="spinner-md"></div>
            <p className="mt-2 text-secondary">Loading jobs...</p>
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-muted">
              No jobs found for this instance.
            </p>
          </div>
        ) : (
          <TableContainer className="border-0">
            <Table>
              <TableHeader>
                <tr>
                  <TableHeaderCell>JOB ID</TableHeaderCell>
                  <TableHeaderCell>STEP ID</TableHeaderCell>
                  <TableHeaderCell>STATUS</TableHeaderCell>
                  <TableHeaderCell>STARTED</TableHeaderCell>
                  <TableHeaderCell>COMPLETED</TableHeaderCell>
                  <TableHeaderCell>DURATION</TableHeaderCell>
                  <TableHeaderCell>RETRIES</TableHeaderCell>
                  <TableHeaderCell align="center">ACTIONS</TableHeaderCell>
                </tr>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell className="font-medium text-xs font-mono">
                      {job.id.slice(0, 8)}...
                    </TableCell>
                    <TableCell>
                      <span className="text-xs px-2 py-1 rounded bg-card">
                        {job.step_id}
                      </span>
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        status={job.status.charAt(0).toUpperCase() + job.status.slice(1)}
                        variant={
                          job.status === 'running' || job.status === 'queued' ? 'info' :
                          job.status === 'completed' ? 'success' :
                          job.status === 'failed' || job.status === 'timeout' ? 'error' :
                          job.status === 'pending' ? 'warning' : 'default'
                        }
                      />
                    </TableCell>
                    <TableCell className="text-muted">
                      {job.started_at ? formatDate(job.started_at) : 'N/A'}
                    </TableCell>
                    <TableCell className="text-muted">
                      {job.completed_at ? formatDate(job.completed_at) :
                       job.status === 'running' || job.status === 'queued' ? 'In progress' : 'N/A'}
                    </TableCell>
                    <TableCell className="text-muted">
                      {job.duration}
                    </TableCell>
                    <TableCell className="text-center">
                      {(job.retry_count || 0) > 0 ? (
                        <span className="px-2 py-1 text-xs rounded bg-warning-subtle text-warning">
                          {job.retry_count}
                        </span>
                      ) : (
                        <span className="text-muted">0</span>
                      )}
                    </TableCell>
                    <TableCell align="center">
                      <div className="flex justify-center space-x-2">
                        <ActionButton
                          variant="navigate"
                          size="sm"
                          onClick={() => {
                            // View job details - could expand or navigate to detail page
                          }}
                        >
                          Details
                        </ActionButton>
                        {job.error_message && (
                          <ActionButton
                            variant="danger"
                            size="sm"
                            onClick={() => {
                              toast({ title: 'Step error', description: job.error_message || 'Unknown error', variant: 'destructive' });
                            }}
                          >
                            View Error
                          </ActionButton>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </div>
    </DashboardLayout>
  );
}
