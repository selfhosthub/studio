// ui/app/workflows/[id]/edit/hooks/useStepCRUD.ts

import { useCallback } from 'react';
import { Step } from '@/entities/workflow';
import { createStepIdFromName, getDependentSteps, topologicalSortSteps } from '@/shared/lib/step-utils';
import { calculateNewStepPosition } from '@/entities/workflow/lib/step-position-utils';
import { usePreferences } from '@/entities/preferences';

const noop = () => {};

export function useStepCRUD(
  workflow: any,
  setWorkflow: React.Dispatch<React.SetStateAction<any>>,
  selectedStepId: string | null,
  setSelectedStepId: React.Dispatch<React.SetStateAction<string | null>>
) {
  const { preferences } = usePreferences();

  // Declared before the null-workflow early return to keep hook order stable across renders.
  const handleStepsChange = useCallback((updatedSteps: Step[]) => {
    setWorkflow((prevWorkflow: any) => ({
      ...prevWorkflow,
      steps: updatedSteps,
      connections: prevWorkflow.connections,
    }));
  }, [setWorkflow]);

  // Return a safe empty shape so the page renders its loading spinner before the workflow loads.
  if (!workflow) {
    return {
      selectedStep: undefined,
      allStepsRecord: {} as Record<string, Step>,
      addStep: noop,
      updateStep: noop,
      handleStepIdChange: noop,
      handleStepsChange,
      removeStep: noop,
      duplicateStep: noop,
    };
  }

  const selectedStep = workflow.steps.find((step: Step) => step.id === selectedStepId);

  const allStepsRecord = workflow.steps.reduce((acc: Record<string, Step>, step: Step) => {
    acc[step.id] = step;
    return acc;
  }, {});

  const addStep = () => {
    const stepName = 'New Step';
    const stepId = createStepIdFromName(stepName, workflow.steps);

    const newPosition = calculateNewStepPosition(
      workflow.steps,
      workflow.connections,
      preferences
    );

    const newStep: Step = {
      id: stepId,
      name: stepName,
      type: 'task',
      position: newPosition,
      ui_config: { position: newPosition },
      parameters: {},
      outputs: {},
      input_mappings: {},
      depends_on: []
    };

    handleStepsChange(topologicalSortSteps([...workflow.steps, newStep]));
    setSelectedStepId(newStep.id);
  };

  const updateStep = (updatedStep: Step) => {
    setWorkflow({
      ...workflow,
      steps: workflow.steps.map((step: Step) =>
        step.id === updatedStep.id ? updatedStep : step
      )
    });
  };

  const handleStepIdChange = (oldId: string, newId: string, serviceId?: string) => {
    setWorkflow((prevWorkflow: any) => {
      const updatedSteps = prevWorkflow.steps.map((step: Step) => {
        if (step.id === oldId) {
          return { ...step, id: newId, ...(serviceId && { service_id: serviceId }) };
        }

        if (step.depends_on!.includes(oldId)) {
          const newDependsOn = step.depends_on!.map((depId: string) =>
            depId === oldId ? newId : depId
          );

          let updatedInputMappings = step.input_mappings;
          if (step.input_mappings) {
            updatedInputMappings = Object.entries(step.input_mappings).reduce(
              (acc: Record<string, any>, [key, mapping]: [string, any]) => {
                if (mapping?.stepId === oldId) {
                  acc[key] = { ...mapping, stepId: newId };
                } else {
                  acc[key] = mapping;
                }
                return acc;
              },
              {}
            );
          }

          return {
            ...step,
            depends_on: newDependsOn,
            input_mappings: updatedInputMappings,
          };
        }

        return step;
      });

      const updatedConnections = prevWorkflow.connections.map((conn: any) => ({
        ...conn,
        source_id: conn.source_id === oldId ? newId : conn.source_id,
        target_id: conn.target_id === oldId ? newId : conn.target_id,
      }));

      return {
        ...prevWorkflow,
        steps: updatedSteps,
        connections: updatedConnections,
      };
    });

    if (selectedStepId === oldId) {
      setSelectedStepId(newId);
    }
  };

  const removeStep = (stepId: string) => {
    const stepsRecord = workflow.steps.reduce((acc: Record<string, any>, step: Step) => {
      acc[step.id] = step;
      return acc;
    }, {});

    const dependents = getDependentSteps(stepId, stepsRecord);

    if (dependents.length > 0) {
      const dependentNames = dependents.map((id: string) => stepsRecord[id].name).join(', ');
      if (!confirm(
        `The following steps depend on "${stepsRecord[stepId].name}":\n\n${dependentNames}\n\nRemoving this step will also remove these dependencies. Continue?`
      )) {
        return;
      }
    }

    const cleanedSteps = workflow.steps
      .filter((step: Step) => step.id !== stepId)
      .map((step: Step) => {
        const cleanedDependsOn = step.depends_on!.filter((dep: string) => dep !== stepId);

        let cleanedInputMappings = step.input_mappings;
        if (step.input_mappings) {
          cleanedInputMappings = Object.entries(step.input_mappings).reduce(
            (acc: Record<string, any>, [key, mapping]: [string, any]) => {
              if (mapping?.stepId !== stepId) {
                acc[key] = mapping;
              }
              return acc;
            },
            {}
          );
        }

        return {
          ...step,
          depends_on: cleanedDependsOn,
          input_mappings: cleanedInputMappings,
        };
      });

    const cleanedConnections = workflow.connections.filter(
      (conn: any) => conn.source_id !== stepId && conn.target_id !== stepId
    );

    setWorkflow({
      ...workflow,
      steps: topologicalSortSteps(cleanedSteps),
      connections: cleanedConnections,
    });

    if (selectedStepId === stepId) {
      const remainingStep = cleanedSteps[0];
      setSelectedStepId(remainingStep?.id || null);
    }
  };

  const duplicateStep = () => {
    if (!selectedStep) return;

    const duplicateStepName = `Copy of ${selectedStep.name}`;
    const duplicateStepId = createStepIdFromName(duplicateStepName, workflow.steps);

    const newStep = {
      ...JSON.parse(JSON.stringify(selectedStep)),
      id: duplicateStepId,
      name: duplicateStepName,
      position: {
        x: (selectedStep.position?.x || 0) + 50,
        y: (selectedStep.position?.y || 0) + 50
      },
      depends_on: []
    };

    handleStepsChange(topologicalSortSteps([...workflow.steps, newStep]));
    setSelectedStepId(newStep.id);
  };

  return {
    selectedStep,
    allStepsRecord,
    addStep,
    updateStep,
    handleStepIdChange,
    handleStepsChange,
    removeStep,
    duplicateStep,
  };
}
