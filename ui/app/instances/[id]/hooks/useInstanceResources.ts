// ui/app/instances/[id]/hooks/useInstanceResources.ts

'use client';

import { useState, useCallback } from 'react';
import {
  getInstance,
  getJobsForInstance,
  getJobResources,
  downloadResource,
  deleteResource,
  regenerateResources,
  regenerateIteration,
  uploadFilesToStep,
} from '@/shared/api';
import { TIMEOUTS } from '@/shared/lib/constants';
import type { InstanceResponse, OrgFile } from '@/shared/types/api';
import { asOutputResources } from '@/shared/api/files';
import { useToast } from '@/features/toast/provider';
import type { Job } from '../lib/types';

interface UseInstanceResourcesParams {
  instanceId: string;
  setInstance: (instance: InstanceResponse | null) => void;
  jobs: Job[];
  setJobs: (jobs: Job[]) => void;
  jobResources: Record<string, OrgFile[]>;
  setJobResources: React.Dispatch<React.SetStateAction<Record<string, OrgFile[]>>>;
}

/**
 * Manages resource-related operations:
 * - Resource selection (for batch operations)
 * - Download, delete, regenerate resources
 * - Regenerate iterations
 * - Upload files to steps
 * - Copy JSON to clipboard
 * - Media viewer modal state
 */
export function useInstanceResources({
  instanceId,
  setInstance,
  jobs,
  setJobs,
  jobResources,
  setJobResources,
}: UseInstanceResourcesParams) {
  const { toast } = useToast();
  // Selection state
  const [selectedResources, setSelectedResources] = useState<Record<string, Set<string>>>({});

  // Media viewer
  const [viewingResource, setViewingResource] = useState<{ resource: OrgFile; allResources: OrgFile[] } | null>(null);

  // Copy feedback
  const [copiedJson, setCopiedJson] = useState<string | null>(null);

  // Operation loading states
  const [deletingResources, setDeletingResources] = useState(false);
  const [regeneratingResources, setRegeneratingResources] = useState(false);

  // --- Selection helpers ---

  const toggleResourceSelection = useCallback((stepId: string, resourceId: string) => {
    setSelectedResources(prev => {
      const stepSelections = prev[stepId] || new Set();
      const newSelections = new Set(stepSelections);
      if (newSelections.has(resourceId)) {
        newSelections.delete(resourceId);
      } else {
        newSelections.add(resourceId);
      }
      return { ...prev, [stepId]: newSelections };
    });
  }, []);

  const getSelectedCount = useCallback((stepId: string): number => {
    return selectedResources[stepId]?.size || 0;
  }, [selectedResources]);

  const clearStepSelection = useCallback((stepId: string) => {
    setSelectedResources(prev => {
      const newState = { ...prev };
      delete newState[stepId];
      return newState;
    });
  }, []);

  // --- Copy JSON ---

  const handleCopyJson = useCallback(async (data: unknown, label: string) => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
      setCopiedJson(label);
      setTimeout(() => setCopiedJson(null), TIMEOUTS.COPY_FEEDBACK);
    } catch {
      // Failed to copy to clipboard
    }
  }, []);

  // --- Download ---

  const handleDownloadResource = useCallback(async (resourceId: string, filename: string) => {
    try {
      const blob = await downloadResource(resourceId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      toast({ title: 'Failed to download file', variant: 'destructive' });
    }
  }, [toast]);

  // --- Upload ---

  const handleUploadFilesToStep = useCallback(async (stepId: string, jobId: string, files: File[]) => {
    try {
      await uploadFilesToStep(instanceId, stepId, files);
      const updatedResources = asOutputResources(await getJobResources(jobId));
      setJobResources(prev => ({ ...prev, [jobId]: updatedResources }));
      toast({ title: `Uploaded ${files.length} file${files.length > 1 ? 's' : ''} successfully`, variant: 'success' });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      toast({ title: `Failed to upload files: ${message}`, variant: 'destructive' });
    }
  }, [instanceId, setJobResources, toast]);

  // --- Delete (selection-based) ---

  const handleDeleteSelectedResources = useCallback(async (stepId: string, jobId: string) => {
    const selectedIds = Array.from(selectedResources[stepId] || []);
    if (selectedIds.length === 0) return;

    if (!confirm(`Delete ${selectedIds.length} selected file${selectedIds.length > 1 ? 's' : ''}? This cannot be undone.`)) {
      return;
    }

    setDeletingResources(true);
    try {
      await Promise.all(selectedIds.map(id => deleteResource(id)));
      setJobResources(prev => ({
        ...prev,
        [jobId]: prev[jobId]?.filter(r => !selectedIds.includes(r.id)) || []
      }));
      clearStepSelection(stepId);
      toast({ title: `Deleted ${selectedIds.length} file${selectedIds.length > 1 ? 's' : ''}`, variant: 'success' });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      toast({ title: `Failed to delete files: ${message}`, variant: 'destructive' });
    } finally {
      setDeletingResources(false);
    }
  }, [selectedResources, setJobResources, clearStepSelection, toast]);

  // --- Delete (ID-based, for SimpleView) ---

  const handleDeleteResourcesWithIds = useCallback(async (stepId: string, jobId: string, resourceIds: string[]) => {
    if (resourceIds.length === 0) return;

    if (!confirm(`Delete ${resourceIds.length} selected file${resourceIds.length > 1 ? 's' : ''}? This cannot be undone.`)) {
      return;
    }

    setDeletingResources(true);
    try {
      await Promise.all(resourceIds.map(id => deleteResource(id)));
      setJobResources(prev => ({
        ...prev,
        [jobId]: prev[jobId]?.filter(r => !resourceIds.includes(r.id)) || []
      }));
      toast({ title: `Deleted ${resourceIds.length} file${resourceIds.length > 1 ? 's' : ''}`, variant: 'success' });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      toast({ title: `Failed to delete files: ${message}`, variant: 'destructive' });
    } finally {
      setDeletingResources(false);
    }
  }, [setJobResources, toast]);

  // --- Regenerate (selection-based) ---

  const handleRegenerateSelectedResources = useCallback(async (stepId: string, jobId: string) => {
    const selectedIds = Array.from(selectedResources[stepId] || []);
    if (selectedIds.length === 0) return;

    if (!confirm(`Regenerate ${selectedIds.length} selected file${selectedIds.length > 1 ? 's' : ''} with new seeds? The old files will be deleted.`)) {
      return;
    }

    setRegeneratingResources(true);
    try {
      // Look up stored iteration params for passthrough regeneration
      const job = jobs.find(j => j.id === jobId);
      const iterRequests = job?.iteration_requests;
      const firstResource = (jobResources[jobId] || []).find(r => selectedIds.includes(r.id));
      const iterIndex = firstResource?.metadata?.iteration_index;

      let overrides: Record<string, unknown> = {};
      if (iterIndex !== undefined && Array.isArray(iterRequests) && iterRequests[iterIndex]?.params) {
        overrides = { ...iterRequests[iterIndex].params };
      }

      await regenerateResources(instanceId, stepId, selectedIds, overrides);

      setJobResources(prev => {
        const newState = { ...prev };
        delete newState[jobId];
        return newState;
      });
      clearStepSelection(stepId);
      toast({ title: `Regenerating ${selectedIds.length} file${selectedIds.length > 1 ? 's' : ''}...`, variant: 'info' });

      const updatedInstance = await getInstance(instanceId);
      setInstance(updatedInstance);
      const jobsData = await getJobsForInstance(instanceId);
      setJobs(jobsData);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      toast({ title: `Failed to regenerate: ${message}`, variant: 'destructive' });
    } finally {
      setRegeneratingResources(false);
    }
  }, [instanceId, jobs, jobResources, selectedResources, setInstance, setJobs, setJobResources, clearStepSelection, toast]);

  // --- Regenerate (ID-based, for SimpleView) ---

  const handleRegenerateResourcesWithIds = useCallback(async (stepId: string, jobId: string, resourceIds: string[]) => {
    if (resourceIds.length === 0) return;

    if (!confirm(`Regenerate ${resourceIds.length} selected file${resourceIds.length > 1 ? 's' : ''} with new seeds? The old files will be deleted.`)) {
      return;
    }

    setRegeneratingResources(true);
    try {
      // Look up stored iteration params for passthrough regeneration
      const job = jobs.find(j => j.id === jobId);
      const iterRequests = job?.iteration_requests;
      const firstResource = (jobResources[jobId] || []).find(r => resourceIds.includes(r.id));
      const iterIndex = firstResource?.metadata?.iteration_index;

      let overrides: Record<string, unknown> = {};
      if (iterIndex !== undefined && Array.isArray(iterRequests) && iterRequests[iterIndex]?.params) {
        overrides = { ...iterRequests[iterIndex].params };
      }

      await regenerateResources(instanceId, stepId, resourceIds, overrides);

      setJobResources(prev => {
        const newState = { ...prev };
        delete newState[jobId];
        return newState;
      });
      toast({ title: `Regenerating ${resourceIds.length} file${resourceIds.length > 1 ? 's' : ''}...`, variant: 'info' });

      const updatedInstance = await getInstance(instanceId);
      setInstance(updatedInstance);
      const jobsData = await getJobsForInstance(instanceId);
      setJobs(jobsData);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      toast({ title: `Failed to regenerate: ${message}`, variant: 'destructive' });
    } finally {
      setRegeneratingResources(false);
    }
  }, [instanceId, jobs, jobResources, setInstance, setJobs, setJobResources, toast]);

  // --- Regenerate iteration ---

  const handleRegenerateIteration = useCallback(async (stepId: string, jobId: string, iterationIndex: number) => {
    if (!confirm(`Regenerate iteration ${iterationIndex + 1}? Existing files for this iteration will be deleted.`)) {
      return;
    }

    setRegeneratingResources(true);
    try {
      // Look up stored iteration params for passthrough regeneration
      const job = jobs.find(j => j.id === jobId);
      const iterRequests = job?.iteration_requests;

      let overrides: Record<string, unknown> = {};
      if (Array.isArray(iterRequests) && iterRequests[iterationIndex]?.params) {
        overrides = { ...iterRequests[iterationIndex].params };
      }

      await regenerateIteration(instanceId, stepId, iterationIndex, overrides);

      setJobResources(prev => {
        const newState = { ...prev };
        delete newState[jobId];
        return newState;
      });
      toast({ title: `Regenerating iteration ${iterationIndex + 1}...`, variant: 'info' });

      const updatedInstance = await getInstance(instanceId);
      setInstance(updatedInstance);
      const jobsData = await getJobsForInstance(instanceId);
      setJobs(jobsData);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      toast({ title: `Failed to regenerate iteration: ${message}`, variant: 'destructive' });
    } finally {
      setRegeneratingResources(false);
    }
  }, [instanceId, jobs, setInstance, setJobs, setJobResources, toast]);

  return {
    // Selection
    selectedResources,
    toggleResourceSelection,
    getSelectedCount,
    clearStepSelection,

    // Media viewer
    viewingResource,
    setViewingResource,

    // Copy
    copiedJson,
    handleCopyJson,

    // Operation states
    deletingResources,
    regeneratingResources,

    // Handlers
    handleDownloadResource,
    handleUploadFilesToStep,
    handleDeleteSelectedResources,
    handleDeleteResourcesWithIds,
    handleRegenerateSelectedResources,
    handleRegenerateResourcesWithIds,
    handleRegenerateIteration,
  };
}
