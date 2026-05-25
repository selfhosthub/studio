// ui/app/instances/[id]/hooks/useInstanceForm.ts

'use client';

import { useEffect, useState, useRef } from 'react';
import {
  getInstance,
  getJobsForInstance,
  getWorkflowFormSchema,
  submitFormAndStart,
  startInstance,
  WorkflowFormSchemaResponse,
} from '@/shared/api';
import { InstanceStatus, type InstanceResponse } from '@/shared/types/api';
import { useToast } from '@/features/toast/provider';
import type { Job } from '../lib/types';

interface UseInstanceFormParams {
  instance: InstanceResponse | null;
  instanceId: string;
  setInstance: (instance: InstanceResponse | null) => void;
  setJobs: (jobs: Job[]) => void;
}

/**
 * Manages form schema loading and submission for pending instances:
 * - Loads workflow form schema when instance is pending
 * - Auto-starts instances with no form fields
 * - Handles form submission to start workflows
 */
export function useInstanceForm({
  instance,
  instanceId,
  setInstance,
  setJobs,
}: UseInstanceFormParams) {
  const { toast } = useToast();
  const [formSchema, setFormSchema] = useState<WorkflowFormSchemaResponse | null>(null);
  const [formSchemaLoading, setFormSchemaLoading] = useState(false);
  const [isSubmittingForm, setIsSubmittingForm] = useState(false);

  // Track if we've already auto-started to prevent double-start in React Strict Mode
  const hasAutoStarted = useRef(false);

  // Load form schema when instance is pending (waiting for user input)
  // If no form fields, auto-start the instance
  useEffect(() => {
    if (!instance || instance.status !== InstanceStatus.Pending) {
      setFormSchema(null);
      return;
    }

    // Check flag synchronously BEFORE any async work
    // This prevents race conditions in React Strict Mode
    if (hasAutoStarted.current) {
      return;
    }
    // Set flag immediately to block concurrent effect executions
    hasAutoStarted.current = true;

    const loadFormSchemaAndMaybeStart = async () => {
      setFormSchemaLoading(true);
      try {
        const schema = await getWorkflowFormSchema(instance.workflow_id);
        if (schema.has_form_fields) {
          // Show form panel for user input - reset flag since we didn't auto-start
          hasAutoStarted.current = false;
          setFormSchema(schema);
        } else {
          // No form fields - auto-start the instance
          const startedInstance = await startInstance(instance.id);
          setInstance(startedInstance);
        }
      } catch {
        // Reset flag on error so user can retry
        hasAutoStarted.current = false;
      } finally {
        setFormSchemaLoading(false);
      }
    };

    loadFormSchemaAndMaybeStart();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- instance fields sufficient, full instance would cause loops
  }, [instance?.workflow_id, instance?.status]);

  // Handle form submission to start the workflow
  const handleFormSubmit = async (formValues: Record<string, unknown>) => {
    setIsSubmittingForm(true);
    try {
      await submitFormAndStart(instanceId, formValues);
      const data = await getInstance(instanceId);
      setInstance(data);
      setFormSchema(null);
      const jobsData = await getJobsForInstance(instanceId);
      setJobs(jobsData);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      toast({ title: `Failed to start workflow: ${message}`, variant: 'destructive' });
    } finally {
      setIsSubmittingForm(false);
    }
  };

  return {
    formSchema,
    formSchemaLoading,
    isSubmittingForm,
    handleFormSubmit,
  };
}
