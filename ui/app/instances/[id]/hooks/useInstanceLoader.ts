// ui/app/instances/[id]/hooks/useInstanceLoader.ts

'use client';

import { useEffect, useState, useRef } from 'react';
import { POLLING } from '@/shared/lib/constants';
import { useParams, useRouter } from 'next/navigation';
import { useUser } from '@/entities/user';
import { useInstanceWebSocket } from '@/features/instances';
import {
  getInstance,
  getJobsForInstance,
  getJobResources,
  getWorkflow,
} from '@/shared/api';
import type { InstanceResponse, OrgFile, WorkflowResponse } from '@/shared/types/api';
import { asOutputResources } from '@/shared/api/files';
import type { Job } from '../lib/types';

/**
 * Loads instance + jobs + resources, subscribes to WebSocket for live updates,
 * polls as fallback when the socket is down, auto-expands running/file-producing
 * jobs, and fetches the workflow for Experience View detection.
 */
export function useInstanceLoader() {
  const params = useParams();
  const router = useRouter();
  const { user, status: authStatus } = useUser();
  const instanceId = params?.id as string;

  const [instance, setInstance] = useState<InstanceResponse | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);

  const [expandedJobs, setExpandedJobs] = useState<Set<string>>(new Set());

  const [jobResources, setJobResources] = useState<Record<string, OrgFile[]>>({});
  const [loadingResources, setLoadingResources] = useState<Set<string>>(new Set());

  const { status: wsStatus, lastEvent } = useInstanceWebSocket(instanceId);

  useEffect(() => {
    console.log('[Loader] WS status →', wsStatus, instanceId);
  }, [wsStatus, instanceId]);

  // Per-session sets - a manually-collapsed job won't auto-expand again.
  const autoExpandedRunningJobs = useRef(new Set<string>());
  const autoExpandedFileJobs = useRef(new Set<string>());
  // Stable ref for effects that shouldn't re-run on every instance change.
  const instanceRef = useRef(instance);
  useEffect(() => { instanceRef.current = instance; }, [instance]);

  useEffect(() => {
    if (authStatus === 'loading') return;
    if (authStatus === 'unauthenticated') {
      router.push('/login');
      return;
    }

    const loadInstance = async () => {
      setLoading(true);
      console.log('[Loader] loading instance', instanceId);
      try {
        const data = await getInstance(instanceId);
        setInstance(data);
        console.log('[Loader] instance loaded', data.status, instanceId);
      } catch {
        console.warn('[Loader] failed to load instance', instanceId);
        // Caller branches on instance === null.
      } finally {
        setLoading(false);
      }
    };

    loadInstance();
  }, [instanceId, authStatus, router]);

  useEffect(() => {
    const workflowId = instance?.workflow_id;
    if (!workflowId) return;

    getWorkflow(workflowId)
      .then(setWorkflow)
      .catch(() => {
        // Workflow may be inaccessible (RBAC); fall back to no Experience View.
      });
  }, [instance?.workflow_id]);

  useEffect(() => {
    if (!lastEvent) return;

    if (lastEvent.event_type === 'instance_data' || lastEvent.event_type === 'instance_status_changed' || lastEvent.event_type === 'instance_step_completed' || lastEvent.event_type === 'instance_step_started' || lastEvent.event_type === 'instance_step_failed' || lastEvent.event_type === 'connection_established') {
      console.log('[Loader] WS event triggered refetch', lastEvent.event_type, instanceId);
      // Fetch together so the filter reads post-event step statuses, not a stale snapshot.
      Promise.all([
        getInstance(instanceId),
        getJobsForInstance(instanceId),
      ]).then(async ([freshInstance, jobsData]) => {
        setInstance(freshInstance);
        setJobs(jobsData);
        console.log('[Loader] refetched instance', freshInstance.status, 'jobs:', jobsData.length);

        const stepsNeedingResources = new Set(
          Object.entries(freshInstance.step_status || {})
            .filter(([, s]) => {
              const lower = String(s).toLowerCase();
              return lower === 'running' || lower === 'completed';
            })
            .map(([id]) => id)
        );

        const jobsToRefresh = jobsData.filter((job: Job) => stepsNeedingResources.has(job.step_id));
        const resourceResults = await Promise.all(
          jobsToRefresh.map(async (job: Job) => {
            try {
              const resources = asOutputResources(await getJobResources(job.id));
              return { jobId: job.id, resources };
            } catch {
              return null;
            }
          })
        );
        const newResources: Record<string, OrgFile[]> = {};
        for (const result of resourceResults) {
          if (result) {
            newResources[result.jobId] = result.resources;
          }
        }
        if (Object.keys(newResources).length > 0) {
          setJobResources(prev => ({ ...prev, ...newResources }));
        }
      }).catch((err: unknown) => { console.error('Failed to refresh instance on WebSocket event:', err); });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- instance accessed for presence check only; refetched data is used for derived sets
  }, [lastEvent, instanceId]);

  useEffect(() => {
    const instanceStatus = instance?.status;
    const isActiveInstance = instance && !['completed', 'failed', 'cancelled', 'pending'].includes(instanceStatus || '');
    const shouldPoll = isActiveInstance && wsStatus !== 'connected';

    if (!shouldPoll) return;

    console.log('[Loader] WS disconnected, starting poll fallback', instanceId);
    const pollInterval = setInterval(async () => {
      // Fetch together so the filter reads the same snapshot.
      const [freshInstance, jobsData] = await Promise.all([
        getInstance(instanceId).catch((err: unknown) => { console.error('Failed to refresh instance during poll:', err); return null; }),
        getJobsForInstance(instanceId).catch(() => []),
      ]);
      console.log('[Loader] poll tick', instanceId, freshInstance?.status);
      if (freshInstance) setInstance(freshInstance);
      setJobs(jobsData);

      // Include completed so a step that just transitioned still gets resources fetched.
      const stepStatusMap = freshInstance?.step_status;
      const runningStepIds = new Set<string>();
      if (stepStatusMap) {
        for (const [stepId, status] of Object.entries(stepStatusMap)) {
          const lower = String(status).toLowerCase();
          if (lower === 'running' || lower === 'completed') {
            runningStepIds.add(stepId);
          }
        }
      }

      if (runningStepIds.size > 0) {
        const jobsToRefresh = jobsData.filter((job: Job) => runningStepIds.has(job.step_id));
        const resourceResults = await Promise.all(
          jobsToRefresh.map(async (job: Job) => {
            try {
              const resources = asOutputResources(await getJobResources(job.id));
              return { jobId: job.id, resources };
            } catch {
              return null;
            }
          })
        );
        const newResources: Record<string, OrgFile[]> = {};
        for (const result of resourceResults) {
          if (result) {
            newResources[result.jobId] = result.resources;
          }
        }
        if (Object.keys(newResources).length > 0) {
          setJobResources(prev => ({ ...prev, ...newResources }));
        }
      }
    }, POLLING.DEFAULT);

    return () => {
      console.log('[Loader] poll fallback stopped', instanceId);
      clearInterval(pollInterval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-poll on status changes
  }, [instance?.status, instance?.step_status, wsStatus, instanceId]);

  // Poll resources for running steps regardless of WS status so partial
  // outputs (e.g. thumbnails generated mid-step) appear progressively.
  useEffect(() => {
    const hasRunningSteps = Object.values(instance?.step_status || {})
      .some(s => String(s).toLowerCase() === 'running');
    if (!hasRunningSteps) return;

    console.log('[Loader] starting resource poll for running steps', instanceId);
    const resourcePollInterval = setInterval(async () => {
      const freshInstance = await getInstance(instanceId).catch(() => null);
      if (!freshInstance) return;
      const runningStepIds = new Set(
        Object.entries(freshInstance.step_status || {})
          .filter(([, s]) => String(s).toLowerCase() === 'running')
          .map(([id]) => id)
      );
      const jobsData = await getJobsForInstance(instanceId).catch(() => [] as Job[]);
      const jobsToRefresh = jobsData.filter((job: Job) => runningStepIds.has(job.step_id));
      const results = await Promise.all(
        jobsToRefresh.map(async (job: Job) => {
          try {
            return { jobId: job.id, resources: asOutputResources(await getJobResources(job.id)) };
          } catch { return null; }
        })
      );
      const newResources: Record<string, OrgFile[]> = {};
      for (const r of results) { if (r) newResources[r.jobId] = r.resources; }
      if (Object.keys(newResources).length > 0) {
        setJobResources(prev => ({ ...prev, ...newResources }));
      }
    }, POLLING.DEFAULT);

    return () => clearInterval(resourcePollInterval);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-evaluate when step statuses change
  }, [instance?.step_status, instanceId]);

  useEffect(() => {
    if (!jobs.length) return;

    const runningJobs = jobs.filter(job =>
      (job.status?.toLowerCase() === 'running' ||
       job.status?.toLowerCase() === 'processing') &&
      !autoExpandedRunningJobs.current.has(job.id)
    );

    if (runningJobs.length > 0) {
      setExpandedJobs(prev => {
        const newSet = new Set(prev);
        for (const job of runningJobs) {
          newSet.add(job.id);
          autoExpandedRunningJobs.current.add(job.id);
        }
        return newSet;
      });
    }
  }, [jobs]);

  useEffect(() => {
    if (!jobs.length) return;

    const completedJobsWithoutResources = jobs.filter(job =>
      (job.status?.toLowerCase() === 'completed') &&
      !jobResources[job.id] &&
      !loadingResources.has(job.id)
    );

    if (completedJobsWithoutResources.length === 0) return;

    for (const job of completedJobsWithoutResources) {
      setLoadingResources(prev => new Set(prev).add(job.id));

      getJobResources(job.id)
        .then(rawResources => {
          const resources = asOutputResources(rawResources);
          setJobResources(prev => ({ ...prev, [job.id]: resources }));
          if (resources.length > 0 && !autoExpandedFileJobs.current.has(job.id)) {
            autoExpandedFileJobs.current.add(job.id);
            setExpandedJobs(prev => new Set([...prev, job.id]));
          }
        })
        .catch((err: unknown) => { console.error('Failed to load resources for completed job:', err); })
        .finally(() => {
          setLoadingResources(prev => {
            const newSet = new Set(prev);
            newSet.delete(job.id);
            return newSet;
          });
        });
    }
  }, [jobs, jobResources, loadingResources]);

  const instanceIdForJobs = instance?.id;
  useEffect(() => {
    if (!instanceIdForJobs) return;

    const loadJobs = async () => {
      setJobsLoading(true);
      try {
        const jobsData = await getJobsForInstance(instanceId);
        setJobs(jobsData);
        console.log('[Loader] jobs loaded', jobsData.length, 'jobs for', instanceId);

        const completedJobs = jobsData.filter((job: Job) => job.status === 'completed' || job.status === 'COMPLETED');
        if (completedJobs.length > 0) {
          const resourcePromises = completedJobs.map(async (job: Job) => {
            try {
              const resources = asOutputResources(await getJobResources(job.id));
              return { jobId: job.id, resources };
            } catch {
              return { jobId: job.id, resources: [] as OrgFile[] };
            }
          });

          const results = await Promise.all(resourcePromises);

          const newResources: Record<string, OrgFile[]> = {};
          const jobsToExpand: string[] = [];

          for (const { jobId, resources } of results) {
            newResources[jobId] = resources;
            if (resources.length > 0 && !autoExpandedFileJobs.current.has(jobId)) {
              jobsToExpand.push(jobId);
              autoExpandedFileJobs.current.add(jobId);
            }
          }

          setJobResources(prev => ({ ...prev, ...newResources }));
          if (jobsToExpand.length > 0) {
            setExpandedJobs(prev => new Set([...prev, ...jobsToExpand]));
          }
        }
      } catch {
        // jobs load failed; render empty state
      } finally {
        setJobsLoading(false);
      }
    };

    loadJobs();
  }, [instanceIdForJobs, instanceId]);

  const toggleJobExpansion = async (jobId: string) => {
    setExpandedJobs(prev => {
      const newSet = new Set(prev);
      if (newSet.has(jobId)) {
        newSet.delete(jobId);
      } else {
        newSet.add(jobId);
        loadJobResources(jobId);
      }
      return newSet;
    });
  };

  const loadJobResources = async (jobId: string) => {
    if (jobResources[jobId] || loadingResources.has(jobId)) return;

    setLoadingResources(prev => new Set(prev).add(jobId));
    try {
      const resources = asOutputResources(await getJobResources(jobId));
      setJobResources(prev => ({ ...prev, [jobId]: resources }));
    } catch {
      setJobResources(prev => ({ ...prev, [jobId]: [] }));
    } finally {
      setLoadingResources(prev => {
        const newSet = new Set(prev);
        newSet.delete(jobId);
        return newSet;
      });
    }
  };

  const hasExperienceView = workflow?.client_metadata?.experience_config != null;

  return {
    instance,
    setInstance,
    workflow,
    loading,
    jobs,
    setJobs,
    jobsLoading,
    instanceId,
    user,
    authStatus,
    wsStatus,
    expandedJobs,
    setExpandedJobs,
    toggleJobExpansion,
    jobResources,
    setJobResources,
    loadingResources,
    hasExperienceView,
    router,
  };
}
