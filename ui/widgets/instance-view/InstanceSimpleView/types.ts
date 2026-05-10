// ui/widgets/instance-view/InstanceSimpleView/types.ts

import type React from "react";
import { DragEndEvent } from "@dnd-kit/core";
import { SensorDescriptor, SensorOptions } from "@dnd-kit/core";
import { OrgFile } from "@/shared/types/api";
import { WorkflowFormSchema } from "@/entities/workflow";
import { CardSize } from "@/entities/organization";

/**
 * Job data from the backend API
 */
export interface Job {
  id: string;
  workflow_instance_id?: string;
  instance_id?: string;
  instance_step_id?: string | null;
  step_id: string;
  step_name?: string;
  status: string;
  result: Record<string, any> | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  retry_count?: number;
  execution_data?: Record<string, any>;
  input_data?: Record<string, any>;
  request_body?: Record<string, any> | null;
  iteration_requests?: Record<string, any>[] | null;
  created_at: string | null;
  updated_at: string | null;
}

/**
 * Workflow step (UI-local shape derived from server-emitted StepExecutionResponse).
 * Worker-side fields (started_at, completed_at, result, retry_count, etc.) are
 * surfaced via the parallel `jobs: Job[]` collection joined on step_id.
 */
export interface WorkflowStep {
  step_id: string;
  name: string;
  depends_on: string[];
  service_id?: string;
  provider_id?: string;
  service_type?: string;
  status: 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'waiting_for_approval' | 'waiting_for_manual_trigger' | 'stopped';
  execution_mode?: 'enabled' | 'skip' | 'stop';
  trigger_type?: 'auto' | 'manual';
  parameters?: Record<string, any>;
  input_mappings?: Record<string, string>;
}

/**
 * Instance data from the backend API
 */
export interface Instance {
  id: string;
  name: string;
  workflow_id: string;
  workflow_name: string;
  status: string;
  error_message?: string;
  error_data?: { error?: string };
  input_data?: Record<string, any>;
  output_data?: {
    pending_approval?: { step_id?: string };
    pending_trigger?: { step_id?: string };
    [key: string]: any;
  };
  created_at: string;
  updated_at: string;
}

/**
 * Selected item in the navigation panel
 */
export type SelectedItem =
  | { type: 'details' }
  | { type: 'inputs' }
  | { type: 'step'; stepId: string };

/**
 * Props for InstanceSimpleView component
 */
export interface InstanceSimpleViewProps {
  instance: any; // Keep as any for compatibility with existing page
  jobs: Job[];
  orderedSteps: WorkflowStep[];
  jobResources: Record<string, OrgFile[]>;
  loadingResources: Set<string>;
  formSchema: WorkflowFormSchema | null;
  onCancel: () => void;
  onRunAgain: () => void;
  onApprove: (approved: boolean) => void;
  onTrigger: (stepId: string) => void;
  onRunStoppedStep: (stepId: string) => void;
  onRetryJob: (jobId: string) => void;
  onRerunJobOnly: (jobId: string) => void;
  onRerunAndContinue: (jobId: string) => void;
  onRerunStepOnly: (instanceId: string, stepId: string) => void;
  onDownloadResource: (resourceId: string, filename: string) => void;
  onUploadFilesToStep?: (stepId: string, jobId: string, files: File[]) => Promise<void>;
  onFormSubmit: (values: Record<string, any>) => void;
  onRegenerateResources: (stepId: string, jobId: string, resourceIds: string[]) => void;
  onRegenerateIteration: (stepId: string, jobId: string, iterationIndex: number) => void;
  onDeleteResources: (stepId: string, jobId: string, resourceIds: string[]) => void;
  onUpdateJobResult?: (jobId: string, result: Record<string, any>) => Promise<void>;
  canCancel: boolean;
  updating: boolean;
  approving: boolean;
  triggering: boolean;
  runningSteps: Set<string>;
  retryingJobs: Set<string>;
  isSubmittingForm: boolean;
  regeneratingResources: boolean;
  deletingResources: boolean;
  /**
   * When true, hide developer-oriented chrome: the "Inputs" left-nav entry
   * and the raw Input/Output JSON blocks inside the Details panel. Step
   * outputs, resource cards, and manual-trigger/approval/regeneration UI
   * still render fully - simple mode is strictly subtractive.
   */
  simpleMode?: boolean;
}

/**
 * Props for ListItem component
 */
export interface ListItemProps {
  icon: React.ReactNode;
  label: string;
  badge?: string | number;
  selected: boolean;
  onClick: () => void;
  status?: string;
  getStatusIcon: (status: string, className?: string) => React.ReactNode;
}

/**
 * Props for JsonSection component
 */
export interface JsonSectionProps {
  id: string;
  title: string;
  data: any;
  fallbackText: string;
  expandedJsonTabs: Set<string>;
  toggleJsonTab: (tabId: string) => void;
  copiedJson: string | null;
  onCopyJson: (data: any, label: string) => void;
}

/**
 * Iteration group for resource display
 */
export interface IterationGroup {
  iterationIndex: number | null;
  resources: OrgFile[];
  expectedCount: number;
  isComplete: boolean;
}

/**
 * Result of grouping resources by iteration
 */
export interface GroupedResources {
  hasIterations: boolean;
  groups: IterationGroup[];
}

/**
 * OrgSettings shape used by resource display components
 */
export interface OrgSettingsShape {
  showThumbnails: boolean;
  resourceCardSize: CardSize;
}

/**
 * Props for the StepPanel component
 */
export interface StepPanelProps {
  selectedStep: WorkflowStep;
  selectedStepExecution: Job | undefined;
  jobs: Job[];
  jobResources: Record<string, OrgFile[]>;
  stepResources: OrgFile[];
  aggregatedResult: Record<string, unknown> | null;
  loadingResources: Set<string>;
  instance: Instance;
  getDisplayStatus: (step: WorkflowStep) => string;
  getExpectedFileCount: (step: WorkflowStep) => number;
  getStatusIcon: (status: string, className?: string) => React.ReactNode;
  stepSelectedIds: Set<string>;
  stepSelectedCount: number;
  localResourceOrder: Record<string, string[]>;
  isReordering: boolean;
  flattenIterations: boolean;
  setFlattenIterations: (value: boolean) => void;
  orgSettings: OrgSettingsShape;
  updateSettings: (updates: Partial<OrgSettingsShape>) => void;
  gridClass: string;
  sensors: SensorDescriptor<SensorOptions>[];
  resultViewMode: "auto" | "tree" | "raw";
  setResultViewMode: (mode: "auto" | "tree" | "raw") => void;
  isDownloading: boolean;
  regeneratingResources: boolean;
  deletingResources: boolean;
  approving: boolean;
  triggering: boolean;
  runningSteps: Set<string>;
  retryingJobs: Set<string>;
  onApprove: (approved: boolean) => void;
  onTrigger: (stepId: string) => void;
  onRunStoppedStep: (stepId: string) => void;
  onRerunJobOnly: (jobId: string) => void;
  onRerunAndContinue: (jobId: string) => void;
  onRerunStepOnly: (instanceId: string, stepId: string) => void;
  onRegenerateResources: (stepId: string, jobId: string, resourceIds: string[]) => void;
  onRegenerateIteration: (stepId: string, jobId: string, iterationIndex: number) => void;
  onDeleteResources: (stepId: string, jobId: string, resourceIds: string[]) => void;
  onDownloadResource: (resourceId: string, filename: string) => void;
  onUploadFilesToStep?: (stepId: string, jobId: string, files: File[]) => Promise<void>;
  handleDownloadFiles: (resources: OrgFile[]) => Promise<void>;
  toggleResourceSelection: (stepId: string, resourceId: string) => void;
  clearSelection: (stepId: string) => void;
  handleDragEnd: (event: DragEndEvent, jobId: string, resources: OrgFile[]) => Promise<void>;
  handleStepDragEnd: (event: DragEndEvent, stepId: string, resources: OrgFile[]) => Promise<void>;
  setViewingResource: (value: { resource: OrgFile; allResources: OrgFile[] } | null) => void;
  calculateDuration: (startedAt: string | null, completedAt: string | null) => string;
  groupResourcesByIteration: (resources: OrgFile[], iterationCount: number | null, filesPerIteration: number) => GroupedResources;
  detectOutputView: (result: Record<string, unknown> | null) => import("@/shared/ui").OutputViewConfig | null;
  onUpdateJobResult?: (jobId: string, result: Record<string, unknown>) => Promise<void>;
  savingResult: boolean;
  setSavingResult: (value: boolean) => void;
  dataViewMode: "auto" | "tree" | "raw";
  setDataViewMode: (mode: "auto" | "tree" | "raw") => void;
  formSchema: WorkflowFormSchema | null;
  orderedSteps: WorkflowStep[];
  /** When true, hide developer panels (Input Data, Request Data) inside step output view. */
  simpleMode?: boolean;
}

/**
 * Props for the StepHeaderActions component
 */
export interface StepHeaderActionsProps {
  selectedStep: WorkflowStep;
  selectedStepExecution: Job | undefined;
  instance: Instance;
  getDisplayStatus: (step: WorkflowStep) => string;
  getStatusIcon: (status: string, className?: string) => React.ReactNode;
  calculateDuration: (startedAt: string | null, completedAt: string | null) => string;
  approving: boolean;
  triggering: boolean;
  runningSteps: Set<string>;
  retryingJobs: Set<string>;
  onApprove: (approved: boolean) => void;
  onTrigger: (stepId: string) => void;
  onRunStoppedStep: (stepId: string) => void;
  onRerunJobOnly: (jobId: string) => void;
  onRerunAndContinue: (jobId: string) => void;
  onRerunStepOnly: (instanceId: string, stepId: string) => void;
}

/**
 * Props for the StepFileToolbar component
 */
export interface StepFileToolbarProps {
  selectedStep: WorkflowStep;
  selectedStepExecution: Job | undefined;
  instance: Instance;
  stepResources: OrgFile[];
  stepSelectedIds: Set<string>;
  stepSelectedCount: number;
  fileCountDisplay: string;
  isDownloading: boolean;
  regeneratingResources: boolean;
  deletingResources: boolean;
  flattenIterations: boolean;
  setFlattenIterations: (value: boolean) => void;
  orgSettings: OrgSettingsShape;
  updateSettings: (updates: Partial<OrgSettingsShape>) => void;
  onRegenerateResources: (stepId: string, jobId: string, resourceIds: string[]) => void;
  onDeleteResources: (stepId: string, jobId: string, resourceIds: string[]) => void;
  handleDownloadFiles: (resources: OrgFile[]) => Promise<void>;
  toggleResourceSelection: (stepId: string, resourceId: string) => void;
  clearSelection: (stepId: string) => void;
  onUploadFilesToStep?: (stepId: string, jobId: string, files: File[]) => Promise<void>;
}

/**
 * Props for the StepDataViewer component
 */
export interface StepDataViewerProps {
  selectedStep: WorkflowStep;
  selectedStepExecution: Job | undefined;
  aggregatedResult: Record<string, unknown> | null;
  hasIterations: boolean;
  flattenIterations: boolean;
  dataViewMode: "auto" | "tree" | "raw";
  setDataViewMode: (mode: "auto" | "tree" | "raw") => void;
  resultViewMode: "auto" | "tree" | "raw";
  setResultViewMode: (mode: "auto" | "tree" | "raw") => void;
  detectOutputView: (result: Record<string, unknown> | null) => import("@/shared/ui").OutputViewConfig | null;
  onUpdateJobResult?: (jobId: string, result: Record<string, unknown>) => Promise<void>;
  savingResult: boolean;
  setSavingResult: (value: boolean) => void;
  /** When true, suppress the Input Data and Request Data sections (developer chrome). */
  simpleMode?: boolean;
  /**
   * Whether this step has any output media resources (images/audio/video files).
   * When true AND simpleMode is true, the Output Data JSON view is suppressed
   * because the playable media above is the canonical user-facing output and
   * the JSON would just duplicate the metadata.
   */
  hasMediaResources?: boolean;
}

/**
 * Props for the ResourceGrid component
 */
export interface ResourceGridProps {
  hasIterations: boolean;
  flattenIterations: boolean;
  groups: IterationGroup[];
  stepResources: OrgFile[];
  selectedStep: WorkflowStep | null;
  selectedStepExecution: Job | undefined;
  localResourceOrder: Record<string, string[]>;
  isReordering: boolean;
  orgSettings: OrgSettingsShape;
  stepSelectedIds: Set<string>;
  showPartialPlaceholders: boolean;
  remainingCount: number;
  gridClass: string;
  sensors: SensorDescriptor<SensorOptions>[];
  toggleResourceSelection: (stepId: string, resourceId: string) => void;
  handleDragEnd: (event: DragEndEvent, jobId: string, resources: OrgFile[]) => Promise<void>;
  handleStepDragEnd: (event: DragEndEvent, stepId: string, resources: OrgFile[]) => Promise<void>;
  setViewingResource: (value: { resource: OrgFile; allResources: OrgFile[] } | null) => void;
  onDownloadResource: (resourceId: string, filename: string) => void;
  onDeleteResources?: (stepId: string, jobId: string, resourceIds: string[]) => void;
}
