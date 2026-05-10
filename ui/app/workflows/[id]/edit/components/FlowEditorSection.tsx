// ui/app/workflows/[id]/edit/components/FlowEditorSection.tsx

'use client';

import React, { useState } from 'react';
import { Plus } from 'lucide-react';
import type { Step } from '@/entities/workflow';
import type { FlexibleConnection } from '@/widgets/flow-editor';
import { FlowEditorWithProvider } from '@/widgets/flow-editor';
import { usePreferences } from '@/entities/preferences';
import { EditorSettingsPanel } from './EditorSettingsPanel';

interface WorkflowForEditor {
  name: string;
  steps: Step[];
  connections: FlexibleConnection[] | null;
}

interface FlowEditorSectionProps {
  workflow: WorkflowForEditor;
  steps: {
    handleStepsChange: (steps: Step[]) => void;
    addStep: () => void;
  };
  connections: {
    handleConnectionsChange: (connections: any) => void;
  };
  selectedStepId: string | null;
  onStepSelect: (id: string | null) => void;
  credentialIssueStepIds: string[];
}

export function FlowEditorSection({
  workflow,
  steps,
  connections,
  selectedStepId,
  onStepSelect,
  credentialIssueStepIds,
}: FlowEditorSectionProps) {
  const { preferences } = usePreferences();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showEditorSettings, setShowEditorSettings] = useState(false);

  const sharedEditorProps = {
    steps: workflow.steps,
    connections: workflow.connections ?? [],
    onStepsChange: steps.handleStepsChange,
    onConnectionsChange: connections.handleConnectionsChange,
    onStepSelect,
    selectedStepId,
    onAddStep: steps.addStep,
    onToggleSettings: () => setShowEditorSettings(!showEditorSettings),
    showSettingsActive: showEditorSettings,
    credentialIssueStepIds,
  };

  if (workflow.steps.length === 0) {
    return (
      <div className="bg-card shadow-sm rounded-lg mb-3 p-12 border border-primary text-center">
        <div className="max-w-md mx-auto">
          <h3 className="text-lg font-medium text-primary mb-2">
            No steps yet
          </h3>
          <p className="text-sm text-muted mb-6">
            Get started by adding your first step to this workflow.
          </p>
          <button
            type="button"
            onClick={steps.addStep}
            className="btn-primary inline-flex items-center px-6 py-3 text-base"
          >
            <Plus className="h-5 w-5 mr-2" />
            Add First Step
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      {/* Fullscreen overlay */}
      {isFullscreen && (
        <div
          className="fixed inset-0 z-50 bg-page flex flex-col"
          onKeyDown={(e) => {
            if (e.key === 'Escape') setIsFullscreen(false);
          }}
          tabIndex={0}
        >
          <div className="flex justify-between items-center p-4 border-b border-primary">
            <div>
              <h2 className="text-xl font-medium text-primary">
                {workflow.name} - Flow Editor
              </h2>
              <p className="text-sm text-secondary">
                Use toolbar buttons (bottom-left) for actions. Press ESC to exit fullscreen.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setIsFullscreen(false)}
              className="btn-secondary"
            >
              Exit Fullscreen
            </button>
          </div>

          {showEditorSettings && (
            <EditorSettingsPanel onClose={() => setShowEditorSettings(false)} />
          )}

          <div className="flex-1 overflow-hidden">
            <FlowEditorWithProvider
              {...sharedEditorProps}
              fullscreen={true}
              onToggleFullscreen={() => setIsFullscreen(false)}
            />
          </div>
        </div>
      )}

      {/* Normal embedded view */}
      <div className="relative bg-card shadow-sm rounded-lg mb-3 p-3 border border-primary">
        <div className="mb-2">
          <div>
            <h2 className="text-base font-medium text-primary">
              Workflow Flow - Click nodes to configure
            </h2>
            <p className="text-xs text-secondary">
              Drag from the right handle (blue circle) of one step to the left handle of another to create connections.
            </p>
          </div>
        </div>

        {showEditorSettings && (
          <EditorSettingsPanel onClose={() => setShowEditorSettings(false)} showEditorHeight />
        )}

        <div style={{ minHeight: `${preferences.defaultEditorHeight}px` }}>
          <FlowEditorWithProvider
            {...sharedEditorProps}
            onToggleFullscreen={() => setIsFullscreen(true)}
          />
        </div>
      </div>
    </>
  );
}
