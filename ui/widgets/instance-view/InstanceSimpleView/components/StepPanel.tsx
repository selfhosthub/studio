// ui/widgets/instance-view/InstanceSimpleView/components/StepPanel.tsx

"use client";

import {
  DndContext,
  closestCenter,
  DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  rectSortingStrategy,
} from "@dnd-kit/sortable";
import {
  Loader2,
  FileText,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { OrgFile } from "@/shared/types/api";
import { FormField } from "@/entities/workflow";
import { INSTANCE_DEFAULTS, STEP_CONFIG_DEFAULTS } from "@/shared/defaults";

import { useState } from "react";
import { StepPanelProps, Job } from "../types";
import {
  normalizeConfig,
  extractDisplayValues,
} from "../utils";
import { StepHeaderActions } from "./StepHeaderActions";
import { StepFileToolbar } from "./StepFileToolbar";
import { StepDataViewer } from "./StepDataViewer";
import { UnifiedIterationBlock } from "./UnifiedIterationBlock";
import { ResourceGrid } from "./ResourceGrid";

export function StepPanel({
  selectedStep,
  selectedStepExecution,
  jobs,
  jobResources,
  stepResources,
  aggregatedResult,
  loadingResources,
  instance,
  getDisplayStatus,
  getExpectedFileCount,
  getStatusIcon,
  stepSelectedIds,
  stepSelectedCount,
  localResourceOrder,
  isReordering,
  flattenIterations,
  setFlattenIterations,
  orgSettings,
  updateSettings,
  gridClass,
  sensors,
  resultViewMode,
  setResultViewMode,
  isDownloading,
  regeneratingResources,
  deletingResources,
  approving,
  triggering,
  runningSteps,
  retryingJobs,
  onApprove,
  onTrigger,
  onRunStoppedStep,
  onRerunJobOnly,
  onRerunAndContinue,
  onRerunStepOnly,
  onRegenerateResources,
  onRegenerateIteration,
  onDeleteResources,
  onDownloadResource,
  onUploadFilesToStep,
  handleDownloadFiles,
  toggleResourceSelection,
  clearSelection,
  handleDragEnd,
  handleStepDragEnd,
  setViewingResource,
  calculateDuration,
  groupResourcesByIteration,
  detectOutputView,
  onUpdateJobResult,
  savingResult,
  setSavingResult,
  dataViewMode,
  setDataViewMode,
  formSchema,
  orderedSteps,
  simpleMode = INSTANCE_DEFAULTS.simpleMode,
}: StepPanelProps) {
  const expectedCount = getExpectedFileCount(selectedStep);
  const isGenerating = selectedStep.status === "running" || loadingResources.has(selectedStepExecution?.id || "");
  const isPending = ["pending", "waiting_for_approval", "waiting_for_manual_trigger"].includes(selectedStep.status);
  const showFullPlaceholders = (isGenerating || isPending) && expectedCount > 0 && stepResources.length === 0 && !regeneratingResources;
  const remainingCount = expectedCount > stepResources.length ? expectedCount - stepResources.length : 0;
  const showPartialPlaceholders = isGenerating && remainingCount > 0 && stepResources.length > 0 && !regeneratingResources;

  // Get iteration info
  const stepJobs = jobs.filter((j: Job) => j.step_id === selectedStep.step_id);
  let iterationCount: number | null = null;

  const iterationJob = stepJobs.find((j: Job) => j.execution_data?.iteration_count);
  if (iterationJob) {
    iterationCount = Number(iterationJob.execution_data?.iteration_count);
  }

  if (!iterationCount && stepResources.length > 0) {
    const maxIterIndex = stepResources.reduce((max: number, r: OrgFile) => {
      const idx = r.metadata?.iteration_index;
      return typeof idx === "number" ? Math.max(max, idx) : max;
    }, -1);
    if (maxIterIndex >= 0) {
      const jobWithCount = stepJobs.find((j: Job) => j.execution_data?.iteration_count);
      iterationCount = jobWithCount
        ? Number(jobWithCount.execution_data?.iteration_count)
        : maxIterIndex + 1;
    }
  }

  if (!iterationCount && stepJobs.length > 1) {
    iterationCount = stepJobs.length;
  }

  const stepParams = selectedStep.parameters || {};
  let filesPerIteration = STEP_CONFIG_DEFAULTS.filesPerIteration;
  if (stepParams.num_images) filesPerIteration = Number(stepParams.num_images) || STEP_CONFIG_DEFAULTS.filesPerIteration;
  else if (stepParams.batch_size) filesPerIteration = Number(stepParams.batch_size) || STEP_CONFIG_DEFAULTS.filesPerIteration;

  const { hasIterations, groups } = groupResourcesByIteration(stepResources, iterationCount, filesPerIteration);

  // Show the Files section when the step actually produces files OR when the
  // user might want to upload a file manually. In technical mode we always
  // show it on completed steps so devs can drop files in; in simple mode we
  // only show it when there's real file content to render - otherwise
  // poll/transform/flow steps would display an empty "Files (0)" header.
  const showFiles = stepResources.length > 0
    || showFullPlaceholders
    || hasIterations
    || (!simpleMode && selectedStep?.status === "completed");

  const fileCountDisplay = (() => {
    if (stepResources.length === 0 && expectedCount > 0) {
      return `(${expectedCount} expected)`;
    }
    if (isGenerating && expectedCount > stepResources.length) {
      return `(${stepResources.length} of ${expectedCount})`;
    }
    return `(${stepResources.length})`;
  })();

  return (
    <div className="p-4 space-y-4">
      {/* Step Header with Actions */}
      <StepHeaderActions
        selectedStep={selectedStep}
        selectedStepExecution={selectedStepExecution}
        instance={instance}
        getDisplayStatus={getDisplayStatus}
        getStatusIcon={getStatusIcon}
        calculateDuration={calculateDuration}
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
      />

      {/* Form Inputs -- shown on the first step so users see what feeds the workflow */}
      {orderedSteps?.[0]?.step_id === selectedStep.step_id && (() => {
        // Use formSchema if available (pending instances), otherwise extract from input_data
        const displayItems = formSchema?.fields && formSchema.fields.length > 0
          ? formSchema.fields.map((field: FormField) => {
              const config = normalizeConfig(field.config);
              const formValueKey = `${field.step_id}.${field.parameter_key}`;
              const value =
                instance.input_data?.form_values?.[formValueKey] ??
                instance.input_data?.[formValueKey] ??
                instance.input_data?.[field.parameter_key] ??
                config.defaultValue ??
                "";
              return { key: formValueKey, label: config.label, value };
            })
          : instance.input_data && Object.keys(instance.input_data).length > 0
            ? extractDisplayValues(instance.input_data)
            : [];
        if (displayItems.length === 0) return null;
        return (
          <FormInputsSection displayItems={displayItems} />
        );
      })()}

      {/* Files Section */}
      {showFiles && (
        <div className="bg-card rounded-lg border border-primary p-4">
          <StepFileToolbar
            selectedStep={selectedStep}
            selectedStepExecution={selectedStepExecution}
            instance={instance}
            stepResources={stepResources}
            stepSelectedIds={stepSelectedIds}
            stepSelectedCount={stepSelectedCount}
            fileCountDisplay={fileCountDisplay}
            isDownloading={isDownloading}
            regeneratingResources={regeneratingResources}
            deletingResources={deletingResources}
            flattenIterations={flattenIterations}
            setFlattenIterations={setFlattenIterations}
            orgSettings={orgSettings}
            updateSettings={updateSettings}
            onRegenerateResources={onRegenerateResources}
            onDeleteResources={onDeleteResources}
            handleDownloadFiles={handleDownloadFiles}
            toggleResourceSelection={toggleResourceSelection}
            clearSelection={clearSelection}
            onUploadFilesToStep={onUploadFilesToStep}
          />

          {showFullPlaceholders && !hasIterations ? (
            <div className={gridClass}>
              {Array.from({ length: expectedCount }).map((_, i) => (
                <div
                  key={`placeholder-${i}`}
                  className="aspect-square bg-card rounded-lg border-2 border-dashed border-primary flex flex-col items-center justify-center"
                >
                  {isGenerating ? (
                    <>
                      <Loader2 className="w-8 h-8 text-muted animate-spin mb-2" />
                      <span className="text-xs text-secondary">Generating...</span>
                    </>
                  ) : (
                    <>
                      <FileText className="w-8 h-8 text-muted mb-2" />
                      <span className="text-xs text-secondary">Pending</span>
                    </>
                  )}
                </div>
              ))}
            </div>
          ) : loadingResources.has(selectedStepExecution?.id || "") ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-muted" />
              <span className="ml-2 text-sm text-secondary">Loading files...</span>
            </div>
          ) : hasIterations && !flattenIterations ? (
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={(e: DragEndEvent) => selectedStepExecution?.instance_step_id && handleStepDragEnd(e, selectedStepExecution.instance_step_id, stepResources)}
            >
              <SortableContext
                items={stepResources.map((r: OrgFile) => r.id)}
                strategy={rectSortingStrategy}
              >
                <div className="space-y-2">
                  {groups.map(({ iterationIndex, resources, expectedCount: groupExpected, isComplete }: { iterationIndex: number | null; resources: OrgFile[]; expectedCount: number; isComplete: boolean }) => {
                    const iterRequest = selectedStepExecution?.iteration_requests?.find(
                      (ir) => (ir as Record<string, unknown>).iteration_index === iterationIndex
                    );
                    const iterFailed = !isComplete
                      && selectedStep.status !== "running"
                      && resources.length === 0;

                    return (
                      <UnifiedIterationBlock
                        key={iterationIndex ?? "ungrouped"}
                        iterationIndex={iterationIndex ?? 0}
                        resources={resources}
                        expectedCount={groupExpected}
                        isComplete={isComplete}
                        requestParams={iterRequest?.params ?? iterRequest ?? null}
                        isGenerating={isGenerating}
                        isFailed={iterFailed}
                        selectedIds={stepSelectedIds}
                        onToggleSelect={(rid: string) => toggleResourceSelection(selectedStep.step_id, rid)}
                        onRegenerateIteration={(idx: number) =>
                          onRegenerateIteration(selectedStep.step_id, selectedStepExecution?.id || "", idx)
                        }
                        onRegenerateSelected={(rids: string[]) =>
                          onRegenerateResources(selectedStep.step_id, selectedStepExecution?.id || "", rids)
                        }
                        onDeleteSelected={(rids: string[]) =>
                          onDeleteResources(selectedStep.step_id, selectedStepExecution?.id || "", rids)
                        }
                        gridClass={gridClass}
                        orgSettings={orgSettings}
                        onViewResource={(r: OrgFile) =>
                          setViewingResource({ resource: r, allResources: stepResources })
                        }
                        onDownloadResource={onDownloadResource}
                        isDragEnabled={selectedStep?.status === "completed" && !isReordering}
                        regenerating={regeneratingResources}
                        deleting={deletingResources}
                        stepStatus={selectedStep.status}
                        viewMode={dataViewMode === "auto" ? "tree" : dataViewMode}
                      />
                    );
                  })}
                </div>
              </SortableContext>
            </DndContext>
          ) : (
            <ResourceGrid
              hasIterations={false}
              flattenIterations={flattenIterations}
              groups={groups}
              stepResources={stepResources}
              selectedStep={selectedStep}
              selectedStepExecution={selectedStepExecution}
              localResourceOrder={localResourceOrder}
              isReordering={isReordering}
              orgSettings={orgSettings}
              stepSelectedIds={stepSelectedIds}
              showPartialPlaceholders={showPartialPlaceholders}
              remainingCount={remainingCount}
              gridClass={gridClass}
              sensors={sensors}
              toggleResourceSelection={toggleResourceSelection}
              handleDragEnd={handleDragEnd}
              handleStepDragEnd={handleStepDragEnd}
              setViewingResource={setViewingResource}
              onDownloadResource={onDownloadResource}
              onDeleteResources={onDeleteResources}
            />
          )}
        </div>
      )}

      {/* JSON Tabs */}
      <StepDataViewer
        selectedStep={selectedStep}
        selectedStepExecution={selectedStepExecution}
        aggregatedResult={aggregatedResult}
        hasIterations={hasIterations}
        flattenIterations={flattenIterations}
        dataViewMode={dataViewMode}
        setDataViewMode={setDataViewMode}
        resultViewMode={resultViewMode}
        setResultViewMode={setResultViewMode}
        detectOutputView={detectOutputView}
        onUpdateJobResult={onUpdateJobResult}
        savingResult={savingResult}
        setSavingResult={setSavingResult}
        simpleMode={simpleMode}
        hasMediaResources={stepResources.length > 0}
      />
    </div>
  );
}

function FormInputsSection({
  displayItems,
}: {
  displayItems: { key: string; label: string; value: unknown }[];
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="bg-card rounded-lg border border-primary overflow-hidden">
      <div
        role="button"
        tabIndex={0}
        onClick={() => setIsExpanded(!isExpanded)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setIsExpanded(!isExpanded); } }}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface transition-colors cursor-pointer"
      >
        <h4 className="text-sm font-medium text-secondary">
          Form Inputs ({displayItems.length})
        </h4>
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-muted" />
        ) : (
          <ChevronRight className="w-4 h-4 text-muted" />
        )}
      </div>
      {isExpanded && (
        <div className="px-4 pb-4 space-y-3">
          {displayItems.map(({ key, label, value }) => (
            <div key={key}>
              <label className="block text-xs font-medium text-secondary mb-1">
                {label}
              </label>
              <div className="px-3 py-2 bg-surface rounded-md border border-primary text-sm text-primary whitespace-pre-wrap">
                {typeof value === "object" ? JSON.stringify(value, null, 2) : (value === "" || value == null) ? <span className="text-muted italic">Not set</span> : String(value)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
