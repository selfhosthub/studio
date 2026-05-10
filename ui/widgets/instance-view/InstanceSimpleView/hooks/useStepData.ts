// ui/widgets/instance-view/InstanceSimpleView/hooks/useStepData.ts

import { useMemo, useCallback } from "react";
import { OrgFile } from "@/shared/types/api";
import { Job, WorkflowStep } from "../types";

interface UseStepDataOptions {
  jobs: Job[];
  jobResources: Record<string, OrgFile[]>;
  orderedSteps: WorkflowStep[];
  instanceStatus: string;
  retryingJobs: Set<string>;
  selectedStepId: string | undefined;
}

interface UseStepDataReturn {
  /** The currently selected step object, or null */
  selectedStep: WorkflowStep | null;
  /**
   * The current StepExecution row for the selected step (carries the
   * worker-attempt fields: started_at, completed_at, result, retry_count,
   * iteration_requests, etc.). Sourced from the parallel `jobs` collection
   * via step_id lookup; each step has at most one row. The most-recent-by-created_at
   * tiebreaker handles any duplicate rows from historical data.
   */
  selectedStepExecution: Job | undefined;
  /** All resources across all jobs for the selected step */
  stepResources: OrgFile[];
  /** Aggregated result from all jobs of the selected step */
  aggregatedResult: Record<string, unknown> | null;
  /** Compute the display status for a step (accounting for retries) */
  getDisplayStatus: (step: WorkflowStep) => string;
  /** Count of resources for a given step */
  getStepResourceCount: (step: WorkflowStep) => number;
  /** Number of expected output files for a step */
  getExpectedFileCount: (step: WorkflowStep) => number;
}

/**
 * Derives step-level display data: selected step/execution references,
 * aggregated resources and results, and display-status helpers.
 */
export function useStepData({
  jobs,
  jobResources,
  orderedSteps,
  instanceStatus,
  retryingJobs,
  selectedStepId,
}: UseStepDataOptions): UseStepDataReturn {
  const selectedStep = selectedStepId
    ? orderedSteps.find((s) => s.step_id === selectedStepId) ?? null
    : null;

  const selectedStepExecution = useMemo(() => {
    if (!selectedStep) return undefined;
    const matching = jobs.filter((j) => j.step_id === selectedStep.step_id);
    if (matching.length === 0) return undefined;
    if (matching.length === 1) return matching[0];
    return [...matching].sort((a, b) => {
      const aT = a.created_at ?? '';
      const bT = b.created_at ?? '';
      return bT.localeCompare(aT);
    })[0];
  }, [selectedStep, jobs]);

  const stepResources = useMemo(() => {
    if (!selectedStep) return [];
    const stepJobs = jobs.filter((j) => j.step_id === selectedStep.step_id);
    const allResources: OrgFile[] = [];
    for (const job of stepJobs) {
      const resources = jobResources[job.id] || [];
      allResources.push(...resources);
    }
    return allResources;
  }, [selectedStep, jobs, jobResources]);

  const aggregatedResult = useMemo((): Record<string, unknown> | null => {
    if (!selectedStep) return null;
    const stepJobs = jobs.filter((j) => j.step_id === selectedStep.step_id);
    if (stepJobs.length === 0) return null;
    if (stepJobs.length === 1) return stepJobs[0].result;

    const sortedJobs = [...stepJobs].sort((a, b) => {
      const aIndex =
        a.execution_data?.iteration_index ??
        a.execution_data?.iteration_config?.current_index ??
        0;
      const bIndex =
        b.execution_data?.iteration_index ??
        b.execution_data?.iteration_config?.current_index ??
        0;
      return aIndex - bIndex;
    });

    const aggregated: Record<string, unknown> = {};
    for (const job of sortedJobs) {
      const result = job.result;
      if (!result || typeof result !== "object") continue;
      for (const [key, value] of Object.entries(result)) {
        if (key in aggregated) {
          const existing = aggregated[key];
          if (Array.isArray(existing) && Array.isArray(value)) {
            aggregated[key] = [...existing, ...value];
          } else if (Array.isArray(existing)) {
            (existing as unknown[]).push(value);
          } else {
            aggregated[key] = [existing, value];
          }
        } else {
          aggregated[key] = value;
        }
      }
    }
    return aggregated;
  }, [selectedStep, jobs]);

  const getDisplayStatus = useCallback(
    (step: WorkflowStep): string => {
      const stepJobs = jobs.filter((j) => j.step_id === step.step_id);
      const instanceTerminated =
        instanceStatus === "cancelled" || instanceStatus === "failed";
      if (!instanceTerminated && stepJobs.some((j) => retryingJobs.has(j.id))) {
        return "running";
      }
      return step.status;
    },
    [jobs, retryingJobs, instanceStatus]
  );

  const getStepResourceCount = useCallback(
    (step: WorkflowStep): number => {
      const stepJobs = jobs.filter((j) => j.step_id === step.step_id);
      return stepJobs.reduce(
        (total, job) => total + (jobResources[job.id]?.length || 0),
        0
      );
    },
    [jobs, jobResources]
  );

  const getExpectedFileCount = useCallback(
    (step: WorkflowStep): number => {
      const serviceType = step.service_type?.toLowerCase() || "";
      const serviceId = step.service_id?.toLowerCase() || "";
      // NOTE: this list intentionally avoids the bare "render" substring -
      // it matched j2v_render (display name "Generate Video"), which submits
      // an async render job and returns project metadata, not file output.
      // Anything that ACTUALLY produces files at the j2v boundary lives in
      // j2v_get_video, which uses a media-specific service_type.
      const fileProducingPatterns = [
        "image_generation",
        "video_generation",
        "audio_generation",
        "text_to_speech",
        "speech_to_text",
        "storage",
        "comfyui",
        "txt2img",
        "img2img",
      ];
      const producesFiles = fileProducingPatterns.some(
        (p) => serviceType.includes(p) || serviceId.includes(p)
      );
      if (!producesFiles) return 0;

      const stepParams = step.parameters || {};

      let perJobCount = 1;
      if (stepParams.num_images) perJobCount = Number(stepParams.num_images) || 1;
      else if (stepParams.batch_size)
        perJobCount = Number(stepParams.batch_size) || 1;
      else if (stepParams.count) perJobCount = Number(stepParams.count) || 1;

      const stepJobs = jobs.filter((j) => j.step_id === step.step_id);
      const jobWithIterRequests = stepJobs.find(
        (j) => j.iteration_requests && j.iteration_requests.length > 0
      );
      if (jobWithIterRequests?.iteration_requests) {
        return perJobCount * jobWithIterRequests.iteration_requests.length;
      }

      const iterationJob = stepJobs.find(
        (j) => j.execution_data?.iteration_count
      );
      if (iterationJob?.execution_data?.iteration_count) {
        return (
          perJobCount *
          (Number(iterationJob.execution_data.iteration_count) || 1)
        );
      }

      if (stepJobs.length > 1) {
        return perJobCount * stepJobs.length;
      }

      return perJobCount;
    },
    [jobs]
  );

  return {
    selectedStep,
    selectedStepExecution,
    stepResources,
    aggregatedResult,
    getDisplayStatus,
    getStepResourceCount,
    getExpectedFileCount,
  };
}
