// ui/app/workflows/builder/hooks/useConnectionHandling.ts

import { useCallback } from 'react';
import { type Step } from '@/entities/workflow';
import {
  buildConnectionSourcesMap,
  syncStepWithConnections,
} from '@/entities/workflow/lib/connection-utils';
import { getUpstreamSteps, createTriggerStep } from '@/shared/lib/step-utils';
import React from 'react';

interface WorkflowState {
  id: string;
  name: string;
  description: string;
  steps: Step[];
  connections: any[];
  status: string;
  trigger_type?: string;
  trigger_input_schema?: Record<string, any>;
}

export function useConnectionHandling(
  workflow: WorkflowState,
  setWorkflow: React.Dispatch<React.SetStateAction<WorkflowState>>,
  selectedStepId: string | null
) {
  // Get connected upstream steps for the selected step (for input mappings)
  const previousSteps: Step[] = React.useMemo(() => {
    const selectedStep = workflow.steps.find((step: Step) => step.id === selectedStepId);
    if (!selectedStep) return [] as Step[];

    const upstreamSteps = getUpstreamSteps(selectedStep.id, workflow.steps) as Step[];

    if (workflow.trigger_type === 'webhook') {
      const triggerStep = createTriggerStep(workflow.trigger_input_schema);
      return [triggerStep, ...upstreamSteps];
    }

    return upstreamSteps;
  }, [selectedStepId, workflow]);

  // Handle connections change from FlowEditor
  // Wraps syncStepWithConnections from connection-utils; handles depends_on sync,
  // template string cleanup, input_mappings cleanup, iteration_config cleanup
  const handleConnectionsChange = useCallback((newConnections: any[]) => {
    setWorkflow(prev => {
      const connectedSourcesMap = buildConnectionSourcesMap(newConnections);

      let stepsChanged = false;
      const updatedSteps = prev.steps.map((step: Step) => {
        const connectedSources = connectedSourcesMap.get(step.id) || new Set<string>();
        const result = syncStepWithConnections(step, connectedSources);
        if (result.changed) stepsChanged = true;
        return result.step;
      });

      return {
        ...prev,
        steps: stepsChanged ? updatedSteps : prev.steps,
        connections: newConnections,
      };
    });
  }, [setWorkflow]);

  return { handleConnectionsChange, previousSteps };
}
