// ui/app/workflows/builder/page.tsx

'use client';

import React, { useState, Suspense, useCallback } from 'react';
import { ArrowLeft, Plus } from 'lucide-react';
import Link from 'next/link';
import { FlowEditorWithProvider, StepConfigPanel, EditorSettingsPanel } from '@/widgets/flow-editor';
import { WorkflowStepConfig } from '@/app/workflows/components/WorkflowStepConfig';
import { usePreferences } from '@/entities/preferences';
import { WorkflowBasicInfoCard } from './components/WorkflowBasicInfoCard';
import { WorkflowActionButtons } from './components/WorkflowActionButtons';
import { useWorkflowEditor } from './hooks/useWorkflowEditor';
import { useConnectionHandling } from './hooks/useConnectionHandling';

function WorkflowBuilderContent() {
  const { preferences } = usePreferences();
  const [showEditorSettings, setShowEditorSettings] = useState(false);
  const [isFlowEditorFullscreen, setIsFlowEditorFullscreen] = useState(false);

  // Refs to FlowEditor functions
  const [fitViewFn, setFitViewFn] = useState<(() => void) | null>(null);
  const [autoArrangeFn, setAutoArrangeFn] = useState<(() => void) | null>(null);

  const handleFitViewRef = useCallback((fn: () => void) => {
    setFitViewFn(() => fn);
  }, []);

  const handleAutoArrangeRef = useCallback((fn: () => void) => {
    setAutoArrangeFn(() => fn);
  }, []);

  const {
    workflow,
    setWorkflow,
    loading,
    loadError,
    isSubmitting,
    selectedStepId,
    setSelectedStepId,
    addStep,
    updateStep,
    handleStepsChange,
    removeStep,
    duplicateStep,
    handleWorkflowPropertyChange,
    saveWorkflow,
  } = useWorkflowEditor();

  const { handleConnectionsChange, previousSteps } = useConnectionHandling(
    workflow,
    setWorkflow,
    selectedStepId
  );

  const selectedStep = workflow.steps.find(step => step.id === selectedStepId);

  const allStepsRecord = workflow.steps.reduce((acc: Record<string, any>, step) => {
    acc[step.id] = step;
    return acc;
  }, {});

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-info"></div>
          <p className="mt-4 text-secondary">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <Link
          href="/workflows/list"
          className="inline-flex items-center text-sm text-info hover:text-info"
        >
          <ArrowLeft className="h-4 w-4 mr-1" />
          Back to Workflows
        </Link>
      </div>


      {loadError && (
        <div className="mb-6 bg-danger-subtle border border-danger rounded-md p-4">
          <p className="text-sm text-danger">{loadError}</p>
        </div>
      )}

      <div className="mb-8">
        <h1 className="text-2xl font-bold text-primary">Workflow Builder</h1>
        <p className="text-muted">Build and configure your workflow</p>
      </div>

      <form onSubmit={saveWorkflow}>
        <WorkflowBasicInfoCard
          name={workflow.name}
          description={workflow.description}
          status={workflow.status}
          onPropertyChange={handleWorkflowPropertyChange}
        />

        {workflow.steps.length > 0 ? (
          <>
            {isFlowEditorFullscreen && (
              <div
                className="fixed inset-0 z-50 bg-card flex flex-col"
                onKeyDown={(e) => {
                  if (e.key === 'Escape') {
                    setIsFlowEditorFullscreen(false);
                  }
                }}
                tabIndex={0}
              >
                <div className="flex justify-between items-center p-4 border-b border-primary">
                  <div>
                    <h2 className="text-xl font-medium text-primary">
                      {workflow.name} - Flow Editor
                    </h2>
                    <p className="text-sm text-secondary">
                      Use toolbar buttons (top-left) for actions. Press ESC to exit fullscreen.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsFlowEditorFullscreen(false)}
                    className="px-4 py-2 bg-input text-primary rounded-md hover:bg-surface"
                  >
                    Exit Fullscreen
                  </button>
                </div>

                {showEditorSettings && (
                  <div className="mx-4 mt-4">
                    <EditorSettingsPanel onClose={() => setShowEditorSettings(false)} />
                  </div>
                )}

                <div className="flex-1 overflow-hidden">
                  <FlowEditorWithProvider
                    steps={workflow.steps}
                    connections={workflow.connections || []}
                    onStepsChange={handleStepsChange}
                    onConnectionsChange={handleConnectionsChange}
                    onStepSelect={setSelectedStepId}
                    selectedStepId={selectedStepId}
                    fullscreen={true}
                    onFitViewRef={handleFitViewRef}
                    onAutoArrangeRef={handleAutoArrangeRef}
                    onAddStep={addStep}
                    onToggleSettings={() => setShowEditorSettings(!showEditorSettings)}
                    onToggleFullscreen={() => setIsFlowEditorFullscreen(false)}
                    showSettingsActive={showEditorSettings}
                  />
                </div>
              </div>
            )}

            <div className="relative bg-card shadow-sm rounded-lg mb-6 p-4 border border-primary">
              <div className="mb-2">
                <h2 className="text-lg font-medium text-primary">
                  Workflow Flow - Click nodes to configure
                </h2>
                <p className="text-xs text-secondary">
                  Drag from the right handle (blue circle) of one step to the left handle of another to create connections.
                </p>
              </div>

              {showEditorSettings && (
                <div className="mb-3">
                  <EditorSettingsPanel
                    onClose={() => setShowEditorSettings(false)}
                    showEditorHeight
                  />
                </div>
              )}

              <div style={{ minHeight: `${preferences.defaultEditorHeight}px` }}>
                <FlowEditorWithProvider
                  steps={workflow.steps}
                  connections={workflow.connections || []}
                  onStepsChange={handleStepsChange}
                  onConnectionsChange={handleConnectionsChange}
                  onStepSelect={setSelectedStepId}
                  selectedStepId={selectedStepId}
                  onFitViewRef={handleFitViewRef}
                  onAutoArrangeRef={handleAutoArrangeRef}
                  onAddStep={addStep}
                  onToggleSettings={() => setShowEditorSettings(!showEditorSettings)}
                  onToggleFullscreen={() => setIsFlowEditorFullscreen(true)}
                  showSettingsActive={showEditorSettings}
                />
              </div>
            </div>
          </>
        ) : (
          <div className="bg-card shadow-sm rounded-lg mb-6 p-12 border border-primary text-center">
            <div className="max-w-md mx-auto">
              <h3 className="text-lg font-medium text-primary mb-2">
                No steps yet
              </h3>
              <p className="text-sm text-secondary mb-6">
                Get started by adding your first step to this workflow.
              </p>
              <button
                type="button"
                onClick={addStep}
                className="btn-primary inline-flex items-center px-6 py-3 text-base"
              >
                <Plus className="h-5 w-5 mr-2" />
                Add First Step
              </button>
            </div>
          </div>
        )}

        <StepConfigPanel
          isOpen={!!selectedStepId && !!selectedStep}
          step={selectedStep || null}
          onClose={() => setSelectedStepId(null)}
          previousSteps={previousSteps}
          allSteps={allStepsRecord}
          stepConfigContent={selectedStep ? (
            <WorkflowStepConfig
              step={selectedStep}
              onUpdate={updateStep}
              onRemove={() => { removeStep(selectedStep.id); setSelectedStepId(null); }}
              onDuplicate={() => duplicateStep(selectedStep)}
              previousSteps={previousSteps}
              allSteps={allStepsRecord}
            />
          ) : null}
        />

        <WorkflowActionButtons
          isSubmitting={isSubmitting}
          cancelHref="/workflows/list"
        />
      </form>
    </div>
  );
}

export default function WorkflowBuilderPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="spinner-md"></div>
          <p className="mt-2 text-sm text-secondary">Loading...</p>
        </div>
      </div>
    }>
      <WorkflowBuilderContent />
    </Suspense>
  );
}
