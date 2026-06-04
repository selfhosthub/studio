// ui/widgets/instance-view/InstanceSimpleView/components/StepDataViewer.tsx

"use client";

import {
  Grid3X3,
  Layers,
  FileText,
} from "lucide-react";
import { OutputViewRenderer } from "@/shared/ui";

import { StepDataViewerProps } from "../types";
import { JsonTreeView } from "./JsonTreeView";
import { JsonRawEditor } from "./JsonRawEditor";
import { IterationRequestSection } from "./IterationRequestSection";

export function StepDataViewer({
  selectedStep,
  selectedStepExecution,
  aggregatedResult,
  hasIterations,
  flattenIterations,
  dataViewMode,
  setDataViewMode,
  resultViewMode,
  setResultViewMode,
  detectOutputView,
  onUpdateJobResult,
  savingResult,
  setSavingResult,
  simpleMode = false,
  hasMediaResources = false,
}: StepDataViewerProps) {
  // In simple mode, hide the Output Data JSON when the step produced media
  // files - the playable thumbnails above are the actual user-facing output
  // and the JSON would just duplicate metadata.
  const hideOutputBlock = simpleMode && hasMediaResources;
  return (
    <div className="space-y-2">
      {/* In simple mode the entire Input + Request developer panel is hidden.
          Output rendering (ResourceCards + the structured Output Data view)
          is unaffected and continues to render below. */}
      {!simpleMode && (
      <>
      {/* View mode toggle for Input/Request data - Fields | Tree | JSON.
          Fields button only renders when one of the inputs has a structured
          shape detectOutputView recognizes (Airtable records, OpenAI choices,
          generic objects with ≥50% displayable values, etc.). When unsupported,
          the toolbar collapses to Tree | JSON for parity with the minimum
          documented in the data-viewer audit. */}
      {(() => {
        const hasAnyData = !!(selectedStepExecution?.input_data || selectedStepExecution?.request_body || selectedStepExecution?.execution_data || (aggregatedResult as Record<string, unknown> | null)?.request_data);
        if (!hasAnyData) return null;

        const inputView = selectedStepExecution?.input_data
          ? detectOutputView(selectedStepExecution.input_data as Record<string, unknown>)
          : null;
        const requestData = (aggregatedResult as Record<string, unknown> | null)?.request_data
          || selectedStepExecution?.request_body
          || selectedStepExecution?.execution_data
          || null;
        const requestView = requestData
          ? detectOutputView(requestData as Record<string, unknown>)
          : null;
        const fieldsAvailable = !!(inputView || requestView);

        return (
          <div className="flex items-center justify-end gap-1 text-xs">
            {fieldsAvailable && (
              <button
                onClick={() => setDataViewMode("auto")}
                className={`px-2 py-1 rounded ${
                  dataViewMode === "auto"
                    ? "bg-info text-white"
                    : "bg-surface text-secondary hover:bg-input"
                }`}
              >
                <Grid3X3 className="w-3 h-3 inline mr-1" />
                Fields
              </button>
            )}
            <button
              onClick={() => setDataViewMode("tree")}
              className={`px-2 py-1 rounded ${
                dataViewMode === "tree"
                  ? "bg-info text-white"
                  : "bg-surface text-secondary hover:bg-input"
              }`}
            >
              <Layers className="w-3 h-3 inline mr-1" />
              Tree
            </button>
            <button
              onClick={() => setDataViewMode("raw")}
              className={`px-2 py-1 rounded ${
                dataViewMode === "raw"
                  ? "bg-info text-white"
                  : "bg-surface text-secondary hover:bg-input"
              }`}
            >
              <FileText className="w-3 h-3 inline mr-1" />
              JSON
            </button>
          </div>
        );
      })()}
      {/* Input Data */}
      {selectedStepExecution?.input_data && (() => {
        const data = selectedStepExecution.input_data;
        const keys = typeof data === "object" && data !== null ? Object.keys(data) : [];
        const hasContext = keys.length > 0 && !(keys.length === 1 && keys[0] === "parameters");
        if (!hasContext) return null;
        const inputDescription = "Input Data is built from this step's configuration and outputs of upstream steps before template resolution. See Request Data for the final resolved values sent to the worker.";
        const inputView = detectOutputView(data as Record<string, unknown>);
        if (dataViewMode === "auto" && inputView) {
          return (
            <OutputViewRenderer
              id={`step-${selectedStep.step_id}-input-fields`}
              result={data}
              outputView={inputView}
              fallbackTitle="Input Data"
            />
          );
        }
        return dataViewMode === "raw" ? (
          <JsonRawEditor
            id={`step-${selectedStep.step_id}-input-raw`}
            title="Input Data (Raw JSON)"
            data={data}
            fallbackText="No input data"
          />
        ) : (
          <JsonTreeView
            id={`step-${selectedStep.step_id}-input`}
            title="Input Data"
            description={inputDescription}
            data={data}
            fallbackText="No input data"
          />
        );
      })()}
      {/* Request Data */}
      {(() => {
        // Skip iteration request display when unified blocks handle it
        if (hasIterations && !flattenIterations) return null;

        const aggregatedRequestData = (aggregatedResult as Record<string, unknown> | null)?.request_data;
        const staticRequestData = selectedStepExecution?.request_body || selectedStepExecution?.execution_data;

        // IterationRequestSection only understands tree | raw; fall back to
        // tree when the toolbar is in auto mode and we hit this path.
        const iterationRequests = selectedStepExecution?.iteration_requests;
        if (flattenIterations && iterationRequests && iterationRequests.length > 0) {
          const iterationViewMode = dataViewMode === "auto" ? "tree" : dataViewMode;
          return (
            <IterationRequestSection
              id={`step-${selectedStep.step_id}-request`}
              iterationRequests={iterationRequests as Array<{ iteration_index: number; params?: Record<string, unknown>; [key: string]: unknown }>}
              viewMode={iterationViewMode}
            />
          );
        }

        const requestData = aggregatedRequestData || staticRequestData;
        if (requestData) {
          const requestView = detectOutputView(requestData as Record<string, unknown>);
          if (dataViewMode === "auto" && requestView) {
            return (
              <OutputViewRenderer
                id={`step-${selectedStep.step_id}-request-fields`}
                result={requestData}
                outputView={requestView}
                fallbackTitle="Request Data"
              />
            );
          }
          return dataViewMode === "raw" ? (
            <JsonRawEditor
              id={`step-${selectedStep.step_id}-request-raw`}
              title="Request Data (Raw JSON)"
              data={requestData}
              fallbackText="No request data"
            />
          ) : (
            <JsonTreeView
              id={`step-${selectedStep.step_id}-request`}
              title="Request Data"
              description="The final resolved parameters sent to the worker after all templates and mappings have been applied."
              data={requestData}
              fallbackText="No request data"
            />
          );
        }

        return null;
      })()}
      </>
      )}
      {aggregatedResult && !hideOutputBlock && (
        <div className="space-y-2">
          {(() => {
            const detectedView = detectOutputView(aggregatedResult);
            if (!detectedView) return null;
            const isKeyValue = detectedView.type === "key_value";
            return (
              <div className="flex items-center justify-end gap-1 text-xs">
                <button
                  onClick={() => setResultViewMode("auto")}
                  className={`px-2 py-1 rounded ${
                    resultViewMode === "auto"
                      ? "bg-info text-white"
                      : "bg-surface text-secondary hover:bg-input"
                  }`}
                >
                  <Grid3X3 className="w-3 h-3 inline mr-1" />
                  {isKeyValue ? "Fields" : "Table"}
                </button>
                <button
                  onClick={() => setResultViewMode("tree")}
                  className={`px-2 py-1 rounded ${
                    resultViewMode === "tree"
                      ? "bg-info text-white"
                      : "bg-surface text-secondary hover:bg-input"
                  }`}
                >
                  <Layers className="w-3 h-3 inline mr-1" />
                  Tree
                </button>
                <button
                  onClick={() => setResultViewMode("raw")}
                  className={`px-2 py-1 rounded ${
                    resultViewMode === "raw"
                      ? "bg-info text-white"
                      : "bg-surface text-secondary hover:bg-input"
                  }`}
                >
                  <FileText className="w-3 h-3 inline mr-1" />
                  JSON
                </button>
              </div>
            );
          })()}
          {resultViewMode === "tree" ? (
            <JsonTreeView
              id={`step-${selectedStep.step_id}-result`}
              title="Output Data"
              data={aggregatedResult}
              fallbackText="No output data"
              editable={selectedStepExecution?.status === "completed" && !!onUpdateJobResult}
              onSave={async (newResult) => {
                if (onUpdateJobResult && selectedStepExecution) {
                  setSavingResult(true);
                  try {
                    await onUpdateJobResult(selectedStepExecution.id, newResult);
                  } finally {
                    setSavingResult(false);
                  }
                }
              }}
              saving={savingResult}
            />
          ) : resultViewMode === "raw" ? (
            <JsonRawEditor
              id={`step-${selectedStep.step_id}-result-raw`}
              title="Output Data (Raw JSON)"
              data={aggregatedResult}
              fallbackText="No output data"
              editable={selectedStepExecution?.status === "completed" && !!onUpdateJobResult}
              onSave={async (newResult) => {
                if (onUpdateJobResult && selectedStepExecution) {
                  setSavingResult(true);
                  try {
                    await onUpdateJobResult(selectedStepExecution.id, newResult);
                  } finally {
                    setSavingResult(false);
                  }
                }
              }}
              saving={savingResult}
            />
          ) : (
            <OutputViewRenderer
              id={`step-${selectedStep.step_id}-result`}
              result={aggregatedResult}
              outputView={detectOutputView(aggregatedResult)}
              fallbackTitle="Output Fields"
            />
          )}
        </div>
      )}
    </div>
  );
}
