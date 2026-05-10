// ui/app/instances/[id]/hooks/useInstanceActions.ts

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  getInstance,
  cancelInstance,
  getJobsForInstance,
  retryJob,
  rerunJobOnly,
  rerunAndContinue,
  rerunStepOnly,
  updateJobResult,
  createInstance,
  resumeInstance,
  approveInstance,
  triggerStep,
  runStoppedStep,
} from '@/shared/api';
import { InstanceStatus, type InstanceResponse } from '@/shared/types/api';
import { useToast } from '@/features/toast/provider';
import type { Job } from '../lib/types';

interface UseInstanceActionsParams {
  instanceId: string;
  instance: InstanceResponse | null;
  setInstance: (instance: InstanceResponse | null) => void;
  jobs: Job[];
  setJobs: (jobs: Job[]) => void;
  setJobResources: React.Dispatch<React.SetStateAction<Record<string, import('@/shared/types/api').OrgFile[]>>>;
}

// Centralises the loading / confirm / API call / reconcile / toast flow for all action handlers.
type LoadingControl =
  | { kind: 'bool'; set: (on: boolean) => void }
  | { kind: 'set'; key: string; set: React.Dispatch<React.SetStateAction<Set<string>>> };

function setLoading(ctrl: LoadingControl, on: boolean): void {
  if (ctrl.kind === 'bool') {
    ctrl.set(on);
    return;
  }
  ctrl.set(prev => {
    const next = new Set(prev);
    if (on) next.add(ctrl.key);
    else next.delete(ctrl.key);
    return next;
  });
}

type ToastFn = (props: { title: string; variant: 'success' | 'destructive' | 'info' }) => void;

interface RunInstanceActionOpts<T> {
  apiCall: () => Promise<T>;
  loading: LoadingControl;
  errorPrefix: string;
  toast: ToastFn;
  confirmMessage?: string;
  onSuccess?: (result: T) => void | Promise<void>;
  successMessage?: string | ((result: T) => string);
  successType?: 'success' | 'info';
  reconcileOnError?: () => Promise<void>;
}

async function runInstanceAction<T>(opts: RunInstanceActionOpts<T>): Promise<void> {
  if (opts.confirmMessage && !window.confirm(opts.confirmMessage)) {
    return;
  }
  console.log('[Action]', opts.errorPrefix.replace('Failed to ', ''), '...');
  setLoading(opts.loading, true);
  try {
    const result = await opts.apiCall();
    if (opts.onSuccess) {
      await opts.onSuccess(result);
    }
    const msg =
      typeof opts.successMessage === 'function'
        ? opts.successMessage(result)
        : opts.successMessage;
    console.log('[Action] success:', msg ?? opts.errorPrefix);
    if (msg) {
      opts.toast({ title: msg, variant: opts.successType ?? 'success' });
    }
  } catch (error: unknown) {
    if (opts.reconcileOnError) {
      await opts.reconcileOnError();
    }
    const message = error instanceof Error ? error.message : 'Unknown error';
    console.warn('[Action] error:', opts.errorPrefix, message);
    opts.toast({ title: `${opts.errorPrefix}: ${message}`, variant: 'destructive' });
  } finally {
    setLoading(opts.loading, false);
  }
}

export function useInstanceActions({
  instanceId,
  instance,
  setInstance,
  jobs,
  setJobs,
  setJobResources,
}: UseInstanceActionsParams) {
  const router = useRouter();
  const { toast } = useToast();

  const [updating, setUpdating] = useState(false);
  const [retryingJobs, setRetryingJobs] = useState<Set<string>>(new Set());
  const [resuming, setResuming] = useState(false);
  const [approving, setApproving] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [runningSteps, setRunningSteps] = useState<Set<string>>(new Set());

  const TERMINAL_STATUSES: InstanceStatus[] = [
    InstanceStatus.Completed,
    InstanceStatus.Failed,
    InstanceStatus.Cancelled,
  ];

  const canCancel = (() => {
    if (!instance) return false;
    const status = instance.status as InstanceStatus;
    if (status === InstanceStatus.Cancelled) return false;
    if (!TERMINAL_STATUSES.includes(status)) return true;
    // PENDING steps don't count as stuck - unreached steps after a stop-mode step would
    // mislead the user; Cancel always 400s in that case.
    const stepStatuses = (instance.step_status || {}) as Record<string, string>;
    return Object.values(stepStatuses).some(s => ['running', 'queued'].includes(s));
  })();

  const canRunAgain = (() => {
    if (!instance) return false;
    const status = instance.status as InstanceStatus;
    if (!TERMINAL_STATUSES.includes(status)) return false;
    const stepStatuses = (instance.step_status || {}) as Record<string, string>;
    return !Object.values(stepStatuses).some(s => ['running', 'pending', 'queued'].includes(s));
  })();

  // Best-effort: swallow errors so the primary action's error toast still shows.
  // Called from rerun/retry error paths; WS broadcast may be delayed on reconnect.
  const reconcileInstanceAndJobs = async (targetInstanceId: string): Promise<void> => {
    try {
      const [updated, jobsData] = await Promise.all([
        getInstance(targetInstanceId),
        getJobsForInstance(targetInstanceId),
      ]);
      setInstance(updated);
      setJobs(jobsData);
    } catch {
      // swallow - WS event or the next poll will catch up
    }
  };

  const refetchInstanceAndJobs = async (targetInstanceId: string): Promise<void> => {
    const [updated, jobsData] = await Promise.all([
      getInstance(targetInstanceId),
      getJobsForInstance(targetInstanceId),
    ]);
    setInstance(updated);
    setJobs(jobsData);
  };

  const handleCancel = () =>
    runInstanceAction({
      apiCall: () => cancelInstance(instanceId),
      loading: { kind: 'bool', set: setUpdating },
      confirmMessage: 'Are you sure you want to cancel this instance?',
      errorPrefix: 'Failed to cancel instance',
      toast,
      onSuccess: async () => {
        const updated = await getInstance(instanceId);
        setInstance(updated);
      },
      successMessage: 'Instance cancelled',
    });

  const handleRetryJob = (jobId: string) =>
    runInstanceAction({
      apiCall: () => retryJob(jobId),
      loading: { kind: 'set', key: jobId, set: setRetryingJobs },
      errorPrefix: 'Failed to retry job',
      toast,
      onSuccess: async () => {
        const jobsData = await getJobsForInstance(instanceId);
        setJobs(jobsData);
      },
      successMessage: 'Job retry initiated',
      successType: 'info',
      reconcileOnError: () => reconcileInstanceAndJobs(instanceId),
    });

  const handleRerunJobOnly = (jobId: string) =>
    runInstanceAction({
      apiCall: () => rerunJobOnly(jobId),
      loading: { kind: 'set', key: jobId, set: setRetryingJobs },
      confirmMessage:
        'Rerun this step?\n\nThis will delete all existing assets from this step and generate new ones.',
      errorPrefix: 'Failed to rerun job',
      toast,
      onSuccess: async () => {
        setJobResources(prev => {
          const newState = { ...prev };
          delete newState[jobId];
          return newState;
        });
        await refetchInstanceAndJobs(instanceId);
      },
      successMessage: 'Step rerun initiated',
      successType: 'info',
      reconcileOnError: () => reconcileInstanceAndJobs(instanceId),
    });

  const handleRerunAndContinue = (jobId: string) =>
    runInstanceAction({
      apiCall: () => rerunAndContinue(jobId),
      loading: { kind: 'set', key: jobId, set: setRetryingJobs },
      confirmMessage:
        'Rerun this step and all downstream steps?\n\nThis will delete all existing assets from this step and all downstream steps.',
      errorPrefix: 'Failed to rerun job',
      toast,
      onSuccess: async () => {
        // Clear all resources since downstream steps will be re-executed too
        setJobResources({});
        await refetchInstanceAndJobs(instanceId);
      },
      successMessage: 'Step rerun initiated (this step + downstream)',
      successType: 'info',
      reconcileOnError: () => reconcileInstanceAndJobs(instanceId),
    });

  const handleRerunStepOnly = (targetInstanceId: string, stepId: string) =>
    runInstanceAction({
      apiCall: () => rerunStepOnly(targetInstanceId, stepId),
      loading: { kind: 'set', key: stepId, set: setRunningSteps },
      confirmMessage:
        'Rerun this step only?\n\nThis will delete all existing assets from this step and generate new ones. Downstream steps will NOT be affected.',
      errorPrefix: 'Failed to rerun step',
      toast,
      onSuccess: async () => {
        // Clear resources for jobs in this step to force reload when it completes
        const stepJobIds = jobs.filter(j => j.step_id === stepId).map(j => j.id);
        setJobResources(prev => {
          const newState = { ...prev };
          for (const jobId of stepJobIds) {
            delete newState[jobId];
          }
          return newState;
        });
        await refetchInstanceAndJobs(targetInstanceId);
      },
      successMessage: 'Step rerun initiated (this step only)',
      successType: 'info',
      reconcileOnError: () => reconcileInstanceAndJobs(targetInstanceId),
    });

  const handleUpdateJobResult = async (jobId: string, result: Record<string, unknown>) => {
    console.log('[Action] updating job result', jobId);
    try {
      await updateJobResult(jobId, result);
      const jobsData = await getJobsForInstance(instanceId);
      setJobs(jobsData);
      toast({ title: 'Output data saved successfully', variant: 'success' });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      toast({ title: `Failed to save output data: ${message}`, variant: 'destructive' });
      throw error; // Re-throw so the component knows it failed
    }
  };

  const handleRunAgain = async () => {
    if (!confirm('Create a new instance with the same configuration?')) {
      return;
    }

    console.log('[Action] creating new instance from', instanceId);
    try {
      const newInstance = await createInstance(
        instance!.workflow_id,
        (instance!.input_data || {}) as Record<string, unknown>,
        {
          source: 'run_again',
          original_instance_id: instance!.id,
          original_name: instance!.name,
        }
      );
      console.log('[Action] new instance created', newInstance.id);
      toast({ title: 'New instance created', variant: 'success' });
      router.push(`/instances/${newInstance.id}`);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      console.warn('[Action] run again failed', message);
      toast({ title: `Failed to create new instance: ${message}`, variant: 'destructive' });
    }
  };

  const handleResumeInstance = () =>
    runInstanceAction({
      apiCall: () => resumeInstance(instanceId),
      loading: { kind: 'bool', set: setResuming },
      errorPrefix: 'Failed to resume instance',
      toast,
      onSuccess: () => refetchInstanceAndJobs(instanceId),
      successMessage: 'Instance resumed',
      successType: 'info',
    });

  const handleApprove = (approved: boolean) =>
    runInstanceAction<unknown>({
      apiCall: () => approveInstance(instanceId, approved),
      loading: { kind: 'bool', set: setApproving },
      confirmMessage: !approved ? 'Are you sure you want to reject this step?' : undefined,
      errorPrefix: `Failed to ${approved ? 'approve' : 'reject'} step`,
      toast,
      onSuccess: () => refetchInstanceAndJobs(instanceId),
      successMessage: (result) =>
        ((result as Record<string, unknown>).message as string) ||
        `Step ${approved ? 'approved' : 'rejected'}`,
    });

  const handleTrigger = (stepId: string) =>
    runInstanceAction({
      apiCall: () => triggerStep(instanceId, stepId),
      loading: { kind: 'bool', set: setTriggering },
      errorPrefix: 'Failed to trigger step',
      toast,
      onSuccess: () => refetchInstanceAndJobs(instanceId),
      successMessage: 'Step triggered',
    });

  const handleRunStoppedStep = (stepId: string) =>
    runInstanceAction({
      apiCall: () => runStoppedStep(instanceId, stepId),
      loading: { kind: 'set', key: stepId, set: setRunningSteps },
      errorPrefix: 'Failed to run step',
      toast,
      onSuccess: () => refetchInstanceAndJobs(instanceId),
      successMessage: 'Step started',
    });

  return {
    // Action states
    updating,
    retryingJobs,
    resuming,
    approving,
    triggering,
    runningSteps,
    canCancel,
    canRunAgain,

    // Action handlers
    handleCancel,
    handleRetryJob,
    handleRerunJobOnly,
    handleRerunAndContinue,
    handleRerunStepOnly,
    handleUpdateJobResult,
    handleRunAgain,
    handleResumeInstance,
    handleApprove,
    handleTrigger,
    handleRunStoppedStep,
  };
}
