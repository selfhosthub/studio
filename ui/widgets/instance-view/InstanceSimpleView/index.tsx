// ui/widgets/instance-view/InstanceSimpleView/index.tsx

"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import {
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import Link from "next/link";
import { StatusBadge } from "@/shared/ui/Table";
import { useOrgSettings } from "@/entities/organization";
import {
  XCircle,
  Info,
  FileText,
} from "lucide-react";
import { InstanceStatus, OrgFile } from "@/shared/types/api";
import { STORAGE_KEYS } from "@/shared/lib/constants";
import { INSTANCE_DEFAULTS } from "@/shared/defaults";
import MediaViewerModal from "../MediaViewerModal";

// Extracted modules
import { InstanceSimpleViewProps, Job, WorkflowStep, SelectedItem } from "./types";
import { ListItem, JsonTreeView, getStatusIcon } from "./components";
import { StepPanel } from "./components/StepPanel";
import { InputsPanel } from "./components/InputsPanel";
import {
  detectOutputView,
  calculateDuration,
  groupResourcesByIteration,
  pickInitialSelection,
} from "./utils";

// Extracted hooks
import { useResizablePanel } from "./hooks/useResizablePanel";
import { useResourceActions } from "./hooks/useResourceActions";
import { useStepData } from "./hooks/useStepData";

export type { InstanceSimpleViewProps, Job, WorkflowStep, SelectedItem };

export default function InstanceSimpleView({
  instance,
  jobs,
  orderedSteps,
  jobResources,
  loadingResources,
  formSchema,
  onCancel,
  onRunAgain,
  onApprove,
  onTrigger,
  onRunStoppedStep,
  onRetryJob,
  onRerunJobOnly,
  onRerunAndContinue,
  onRerunStepOnly,
  onDownloadResource,
  onUploadFilesToStep,
  onFormSubmit,
  onRegenerateResources,
  onRegenerateIteration,
  onDeleteResources,
  onUpdateJobResult,
  canCancel,
  updating,
  approving,
  triggering,
  runningSteps,
  retryingJobs,
  isSubmittingForm,
  regeneratingResources,
  deletingResources,
  simpleMode = INSTANCE_DEFAULTS.simpleMode,
}: InstanceSimpleViewProps) {
  const { settings: orgSettings, updateSettings } = useOrgSettings();
  const [savingResult, setSavingResult] = useState(false);

  // --- Panel resize ---
  const { panelWidth, isLargeScreen, containerRef, handleMouseDown } = useResizablePanel({
    storageKey: STORAGE_KEYS.INSTANCE_PANEL_WIDTH,
  });

  // --- Resource actions (download, selection, reorder) ---
  const {
    localResourceOrder,
    isReordering,
    isDownloading,
    selectedResourceIds,
    toggleResourceSelection,
    clearSelection,
    handleDownloadFiles,
    handleDragEnd,
    handleStepDragEnd,
  } = useResourceActions({ onDownloadResource });

  // Grid classes based on card size
  const gridClass = useMemo(() => {
    switch (orgSettings.resourceCardSize) {
      case "small":
        return "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3";
      case "large":
        return "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 gap-4";
      default:
        return "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3";
    }
  }, [orgSettings.resourceCardSize]);

  // Compute display status that reflects current activity
  const displayStatus = useMemo(() => {
    if (regeneratingResources) return "processing";
    if (retryingJobs.size > 0) return "processing";
    const hasRunningStep = orderedSteps.some((step) => step.status === "running");
    if (hasRunningStep) return "running";
    return instance.status;
  }, [regeneratingResources, retryingJobs, orderedSteps, instance.status]);

  // Pre-submission = the instance is waiting for form submission. The
  // backend signals this via status === 'pending': lifecycle_service sets
  // PENDING at creation for QUEUED workflows, and useInstanceForm only
  // loads formSchema when status === 'pending'. In that state the form
  // IS the primary UI - surface it even in simple mode. Once the user
  // submits and the workflow actually starts (status transitions away
  // from 'pending'), simple mode reverts to hiding inputs as intended.
  //
  // Jobs.length isn't a usable signal: lifecycle_service.create_instance
  // pre-creates job rows (all PENDING status) alongside the instance, so
  // jobs.length > 0 even before submission.
  const isPreSubmission = instance.status === InstanceStatus.Pending;
  const hasInstanceInputs = Boolean(
    instance.input_data && Object.keys(instance.input_data).length > 0
  );
  const hasFormFieldsLoaded = (formSchema?.fields?.length || 0) > 0;

  const [selectedItem, setSelectedItem] = useState<SelectedItem>(() =>
    pickInitialSelection({
      simpleMode,
      isPreSubmission,
      hasInputs: hasFormFieldsLoaded || hasInstanceInputs,
      orderedSteps,
    })
  );

  const [viewingResource, setViewingResource] = useState<{
    resource: OrgFile;
    allResources: OrgFile[];
  } | null>(null);
  const [formValues, setFormValues] = useState<Record<string, unknown>>({});
  const [resultViewMode, setResultViewMode] = useState<"auto" | "tree" | "raw">(INSTANCE_DEFAULTS.resultViewMode);
  const [dataViewMode, setDataViewMode] = useState<"auto" | "tree" | "raw">(INSTANCE_DEFAULTS.dataViewMode);
  // Default to flattened iterations in simple mode; per-iteration grouping is
  // a developer-debug concern not useful to end users.
  const [flattenIterations, setFlattenIterations] = useState(simpleMode);
  const hasUserNavigated = useRef(false);

  // When formSchema loads async after mount, navigate to the inputs pane.
  // In technical mode this always applies. In simple mode it applies only
  // in pre-submission - post-submission the user shouldn't be bounced into
  // a tab they can't see.
  const prevFormSchemaRef = useRef(formSchema);
  useEffect(() => {
    if (simpleMode && !isPreSubmission) return;
    if (hasUserNavigated.current) return;
    if (prevFormSchemaRef.current === formSchema) return;
    prevFormSchemaRef.current = formSchema;
    const hasFormInputs =
      (formSchema?.fields?.length || 0) > 0 ||
      (instance.input_data && Object.keys(instance.input_data).length > 0);
    if (hasFormInputs) {
      setSelectedItem({ type: "inputs" }); // eslint-disable-line react-hooks/set-state-in-effect -- async prop arrival
    }
  }, [formSchema, instance.input_data, simpleMode, isPreSubmission]);

  // Dnd-kit sensors for drag-and-drop
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  // --- Step data derivation ---
  const selectedStepId = selectedItem.type === "step" ? selectedItem.stepId : undefined;

  const {
    selectedStep,
    selectedStepExecution,
    stepResources,
    aggregatedResult,
    getDisplayStatus,
    getStepResourceCount,
    getExpectedFileCount,
  } = useStepData({
    jobs,
    jobResources,
    orderedSteps,
    instanceStatus: instance.status,
    retryingJobs,
    selectedStepId,
  });

  const formFieldCount = formSchema?.fields?.length || 0;
  const hasInputs =
    formFieldCount > 0 || (instance.input_data && Object.keys(instance.input_data).length > 0);

  const stepSelectedIds = selectedStep
    ? selectedResourceIds[selectedStep.step_id] || new Set<string>()
    : new Set<string>();
  const stepSelectedCount = stepSelectedIds.size;

  return (
    <div className="flex flex-col h-full">
      {/* Header Row */}
      <div className="flex flex-wrap items-center gap-3 p-4 bg-surface border-b border-primary">
        <h2 className="text-lg font-semibold text-primary truncate">
          {instance.name || "Instance"}
        </h2>
        <StatusBadge status={displayStatus} />
        {/* Pending approval step link */}
        {(() => {
          const pendingApprovalStepId = instance.output_data?.pending_approval?.step_id;
          const approvalStep = pendingApprovalStepId
            ? orderedSteps.find((s) => s.step_id === pendingApprovalStepId)
            : null;
          if (instance.status !== InstanceStatus.WaitingForApproval || !approvalStep) return null;
          return (
            <button
              onClick={() => setSelectedItem({ type: "step", stepId: approvalStep.step_id })}
              className="text-info hover:text-info hover:underline font-medium text-sm"
            >
              {approvalStep.name}
            </button>
          );
        })()}
        {/* Pending trigger step link */}
        {(() => {
          const pendingTriggerStepId = instance.output_data?.pending_trigger?.step_id;
          const pendingStep = pendingTriggerStepId
            ? orderedSteps.find((s) => s.step_id === pendingTriggerStepId)
            : null;
          if (instance.status !== InstanceStatus.WaitingForManualTrigger || !pendingStep) return null;
          return (
            <button
              onClick={() => setSelectedItem({ type: "step", stepId: pendingStep.step_id })}
              className="text-info hover:text-info hover:underline font-medium text-sm"
            >
              {pendingStep.name}
            </button>
          );
        })()}
      </div>

      {/* Main Content - Split Panel */}
      <div ref={containerRef} className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        {/* Left Panel - Navigation List */}
        <div
          className="w-full flex-shrink-0 border-b lg:border-b-0 border-primary bg-card overflow-y-auto"
          style={isLargeScreen ? { width: panelWidth } : undefined}
        >
          <div
            className="p-3 space-y-1"
            onClick={() => {
              hasUserNavigated.current = true;
            }}
          >
            <ListItem
              icon={<Info className="w-5 h-5" />}
              label="Details"
              selected={selectedItem.type === "details"}
              onClick={() => setSelectedItem({ type: "details" })}
            />

            {hasInputs && (!simpleMode || isPreSubmission) && (
              <ListItem
                icon={<FileText className="w-5 h-5" />}
                label="Inputs"
                badge={formFieldCount || Object.keys(instance.input_data || {}).length}
                selected={selectedItem.type === "inputs"}
                onClick={() => setSelectedItem({ type: "inputs" })}
              />
            )}

            <div className="h-px bg-input my-2" />

            <div className="text-xs font-medium text-secondary px-3 py-1">
              Steps ({orderedSteps.length})
            </div>
            {orderedSteps.map((step, index) => (
              <ListItem
                key={step.step_id}
                icon={
                  <span
                    className={`w-5 h-5 flex items-center justify-center text-xs font-medium rounded-full ${ // css-check-ignore -- step-status visualization
                      getDisplayStatus(step) === "completed"
                        ? "bg-success-subtle text-success"
                        : getDisplayStatus(step) === "failed"
                          ? "bg-danger-subtle text-danger"
                          : getDisplayStatus(step) === "running"
                            ? "bg-info-subtle text-info"
                            : "bg-surface text-secondary"
                    }`}
                  >
                    {index + 1}
                  </span>
                }
                label={step.name}
                badge={getStepResourceCount(step) > 0 ? `${getStepResourceCount(step)}` : undefined}
                selected={selectedItem.type === "step" && selectedItem.stepId === step.step_id}
                onClick={() => setSelectedItem({ type: "step", stepId: step.step_id })}
                status={getDisplayStatus(step)}
                triggerType={step.trigger_type}
                executionMode={step.execution_mode}
              />
            ))}
          </div>
        </div>

        {/* Resize Handle */}
        <div
          onMouseDown={handleMouseDown}
          className="hidden lg:flex w-1 cursor-col-resize hover:bg-[var(--theme-primary)] active:bg-[var(--theme-primary)] flex-shrink-0 transition-colors"
          title="Drag to resize"
        />

        {/* Right Panel - Content */}
        <div className="flex-1 overflow-y-auto bg-surface">
          {/* Details Panel */}
          {selectedItem.type === "details" && (
            <DetailsPanel instance={instance} displayStatus={displayStatus} simpleMode={simpleMode} />
          )}

          {/* Inputs Panel */}
          {selectedItem.type === "inputs" && (
            <InputsPanel
              instance={instance}
              formSchema={formSchema}
              formValues={formValues}
              setFormValues={setFormValues}
              onFormSubmit={onFormSubmit}
              isSubmittingForm={isSubmittingForm}
            />
          )}

          {/* Step Panel */}
          {selectedItem.type === "step" && selectedStep && (
            <StepPanel
              selectedStep={selectedStep}
              selectedStepExecution={selectedStepExecution}
              jobs={jobs}
              jobResources={jobResources}
              stepResources={stepResources}
              aggregatedResult={aggregatedResult}
              loadingResources={loadingResources}
              instance={instance}
              getDisplayStatus={getDisplayStatus}
              getExpectedFileCount={getExpectedFileCount}
              getStatusIcon={getStatusIcon}
              stepSelectedIds={stepSelectedIds}
              stepSelectedCount={stepSelectedCount}
              localResourceOrder={localResourceOrder}
              isReordering={isReordering}
              flattenIterations={flattenIterations}
              setFlattenIterations={setFlattenIterations}
              orgSettings={orgSettings}
              updateSettings={updateSettings}
              gridClass={gridClass}
              sensors={sensors}
              resultViewMode={resultViewMode}
              setResultViewMode={setResultViewMode}
              isDownloading={isDownloading}
              regeneratingResources={regeneratingResources}
              deletingResources={deletingResources}
              approving={approving}
              triggering={triggering}
              runningSteps={runningSteps}
              retryingJobs={retryingJobs}
              onApprove={onApprove}
              onTrigger={onTrigger}
              onRunStoppedStep={onRunStoppedStep}
              onRerunJobOnly={onRerunJobOnly}
              onRerunAndContinue={onRerunAndContinue}
              onRerunStepOnly={onRerunStepOnly}
              onRegenerateResources={onRegenerateResources}
              onRegenerateIteration={onRegenerateIteration}
              onDeleteResources={onDeleteResources}
              onDownloadResource={onDownloadResource}
              onUploadFilesToStep={onUploadFilesToStep}
              handleDownloadFiles={handleDownloadFiles}
              toggleResourceSelection={toggleResourceSelection}
              clearSelection={clearSelection}
              handleDragEnd={handleDragEnd}
              handleStepDragEnd={handleStepDragEnd}
              setViewingResource={setViewingResource}
              calculateDuration={calculateDuration}
              groupResourcesByIteration={groupResourcesByIteration}
              detectOutputView={detectOutputView}
              onUpdateJobResult={onUpdateJobResult}
              savingResult={savingResult}
              setSavingResult={setSavingResult}
              dataViewMode={dataViewMode}
              setDataViewMode={setDataViewMode}
              formSchema={formSchema}
              orderedSteps={orderedSteps}
              simpleMode={simpleMode}
            />
          )}
        </div>
      </div>

      {/* Media Viewer Modal */}
      {viewingResource && (
        <MediaViewerModal
          resource={viewingResource.resource}
          resources={viewingResource.allResources}
          onClose={() => setViewingResource(null)}
          onDownload={onDownloadResource}
          onNavigate={(r) =>
            setViewingResource({ resource: r, allResources: viewingResource.allResources })
          }
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline sub-components for Details and Inputs panels (render-only, no hooks)
// ---------------------------------------------------------------------------

function DetailsPanel({
  instance,
  displayStatus,
  simpleMode = false,
}: {
  instance: InstanceSimpleViewProps["instance"];
  displayStatus: string;
  simpleMode?: boolean;
}) {
  return (
    <div className="p-4 space-y-4">
      {instance.status === InstanceStatus.Failed && (instance.error_message || instance.error_data?.error) && (
        <div className="alert alert-error">
          <div className="flex items-start gap-3">
            <XCircle className="w-5 h-5 text-danger flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-medium text-danger">Instance Failed</div>
              <div className="text-sm text-danger mt-1">
                {instance.error_message || instance.error_data?.error}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="bg-card rounded-lg border border-primary p-4">
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <dt className="text-sm font-medium text-secondary">Name</dt>
            <dd className="mt-1 text-sm text-primary">{instance.name}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-secondary">Status</dt>
            <dd className="mt-1">
              <StatusBadge status={displayStatus} />
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-secondary">Workflow</dt>
            <dd className="mt-1 text-sm">
              <Link
                href={`/workflows/${instance.workflow_id}`}
                className="text-info hover:text-info hover:underline"
              >
                {instance.workflow_name}
              </Link>
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-secondary">Runtime</dt>
            <dd className="mt-1 text-sm text-primary">
              {calculateDuration(instance.created_at, instance.updated_at)}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-secondary">Created</dt>
            <dd className="mt-1 text-sm text-primary">
              {new Date(instance.created_at).toLocaleString()}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-secondary">Updated</dt>
            <dd className="mt-1 text-sm text-primary">
              {new Date(instance.updated_at).toLocaleString()}
            </dd>
          </div>
        </dl>
      </div>

      {!simpleMode && (
        <div className="space-y-2">
          <JsonTreeView
            id="details-input"
            title="Input Data"
            data={instance.input_data}
            fallbackText="No input data"
          />
          <JsonTreeView
            id="details-output"
            title="Output Data"
            data={instance.output_data}
            fallbackText="No output data"
          />
        </div>
      )}
    </div>
  );
}

