// ui/app/(authenticated)/instances/[id]/hooks/useInstanceLoader.ts

'use client';

import { useCallback, useEffect, useState, useRef } from 'react';
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

  // Per-session sets - a manually-collapsed job won't auto-expand again.
  const autoExpandedRunningJobs = useRef(new Set<string>());
  const autoExpandedFileJobs = useRef(new Set<string>());
  // Monotonic staleness guard for refetchSnapshot. WS-event-driven and poll
  // refetches overlap; without ordering an older snapshot resolving after a
  // newer one clobbers fresh state (image count 5->4->5, status flipping out of
  // a terminal). The backend is monotonic, so a later-issued refetch always
  // queries equal-or-newer server state: apply only the most-recently-issued
  // refetch's results, dropping any that a newer refetch has already superseded.
  const refetchSeq = useRef(0);
  const appliedSeq = useRef(0);
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
      try {
        const data = await getInstance(instanceId);
        setInstance(data);
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

  // Refetch instance + jobs, then resources for steps that are running/completed.
  // Each fetch degrades independently: instance reject keeps the prior instance,
  // jobs reject falls back to [].
  const refetchSnapshot = useCallback(async () => {
    const mySeq = ++refetchSeq.current;
    const [freshInstance, jobsData] = await Promise.all([
      getInstance(instanceId).catch((err: unknown) => { console.error('Failed to refresh instance:', err); return null; }),
      getJobsForInstance(instanceId).catch((err: unknown) => { console.error('Failed to refresh instance:', err); return [] as Job[]; }),
    ]);
    // Drop this snapshot if a newer refetch has already applied while we awaited.
    if (mySeq < appliedSeq.current) return;
    appliedSeq.current = mySeq;
    if (freshInstance) setInstance(freshInstance);
    setJobs(jobsData);

    const stepsNeedingResources = new Set(
      Object.entries(freshInstance?.step_status || {})
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
          return { jobId: job.id, resources: asOutputResources(await getJobResources(job.id)) };
        } catch {
          return null;
        }
      })
    );
    // Re-check: the resource fetch is a second await, so a newer refetch may
    // have superseded us in the interim. Drop stale resources too.
    if (mySeq < appliedSeq.current) return;
    appliedSeq.current = mySeq;
    const newResources: Record<string, OrgFile[]> = {};
    for (const result of resourceResults) {
      if (result) newResources[result.jobId] = result.resources;
    }
    if (Object.keys(newResources).length > 0) {
      setJobResources(prev => ({ ...prev, ...newResources }));
    }
  }, [instanceId]);

  useEffect(() => {
    if (!lastEvent) return;
    if (lastEvent.event_type === 'instance_data' || lastEvent.event_type === 'instance_status_changed' || lastEvent.event_type === 'instance_step_completed' || lastEvent.event_type === 'instance_step_started' || lastEvent.event_type === 'instance_step_failed' || lastEvent.event_type === 'connection_established') {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- setState is async, inside refetchSnapshot's awaited fetch
      void refetchSnapshot();
    }
  }, [lastEvent, refetchSnapshot]);

  // Refetch on tab-return: backgrounding throttles WS delivery without dropping
  // the socket, so events can be missed while wsStatus stays 'connected'.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      const status = instanceRef.current?.status;
      if (status && ['completed', 'failed', 'cancelled'].includes(status)) return;
      void refetchSnapshot();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [refetchSnapshot]);

  // Reconcile poll: runs while the instance is non-terminal, regardless of
  // wsStatus, to catch dropped/coalesced events. Interval scales with state -
  // FAST while disconnected, DEFAULT while a step is running, SLOW while parked.
  useEffect(() => {
    const instanceStatus = instance?.status;
    const isActiveInstance = instance && !['completed', 'failed', 'cancelled', 'pending'].includes(instanceStatus || '');
    if (!isActiveInstance) return;

    const hasRunningStep = Object.values(instance?.step_status || {})
      .some(s => String(s).toLowerCase() === 'running');
    const interval = wsStatus !== 'connected'
      ? POLLING.FAST
      : hasRunningStep ? POLLING.DEFAULT : POLLING.SLOW;

    const pollInterval = setInterval(() => { void refetchSnapshot(); }, interval);

    return () => clearInterval(pollInterval);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-run only on status/step-status change, not every instance mutation
  }, [instance?.status, instance?.step_status, wsStatus, refetchSnapshot]);

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

    // IIFE so the loading-marker set isn't read as a synchronous set within the
    // effect body. The loop body still runs synchronously (no await before the
    // marker), so timing/behavior is unchanged.
    void (async () => {
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
    })();
  }, [jobs, jobResources, loadingResources]);

  const instanceIdForJobs = instance?.id;
  useEffect(() => {
    if (!instanceIdForJobs) return;

    const loadJobs = async () => {
      setJobsLoading(true);
      try {
        const jobsData = await getJobsForInstance(instanceId);
        setJobs(jobsData);

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
