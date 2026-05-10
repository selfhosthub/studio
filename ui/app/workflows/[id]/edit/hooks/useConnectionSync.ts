// ui/app/workflows/[id]/edit/hooks/useConnectionSync.ts

import React, { useCallback } from 'react';
import { Step } from '@/entities/workflow';
import { buildConnectionSourcesMap, syncStepWithConnections } from '@/entities/workflow/lib/connection-utils';
import { getUpstreamSteps, createTriggerStep, topologicalSortSteps } from '@/shared/lib/step-utils';

export function useConnectionSync(
  workflow: any,
  setWorkflow: React.Dispatch<React.SetStateAction<any>>,
  selectedStepId: string | null
) {
  const previousSteps: Step[] = React.useMemo(() => {
    const selectedStep = workflow?.steps.find((step: Step) => step.id === selectedStepId);
    if (!selectedStep || !workflow) return [] as Step[];

    const upstreamSteps = getUpstreamSteps(selectedStep.id, workflow.steps) as Step[];

    if (workflow.trigger_type === 'webhook') {
      const triggerStep = createTriggerStep(workflow.trigger_input_schema);
      return [triggerStep, ...upstreamSteps];
    }

    return upstreamSteps;
  }, [selectedStepId, workflow]);

  const handleConnectionsChange = useCallback((newConnections: any[]) => {
    setWorkflow((prevWorkflow: any) => {
      const connectedSourcesMap = buildConnectionSourcesMap(newConnections);

      let stepsChanged = false;
      const updatedSteps = prevWorkflow.steps.map((step: Step) => {
        const connectedSources = connectedSourcesMap.get(step.id) || new Set<string>();
        const result = syncStepWithConnections(step, connectedSources);
        if (result.changed) stepsChanged = true;
        return result.step;
      });

      return {
        ...prevWorkflow,
        steps: stepsChanged ? topologicalSortSteps(updatedSteps) : prevWorkflow.steps,
        connections: newConnections
      };
    });
  }, [setWorkflow]);

  return { handleConnectionsChange, previousSteps };
}
