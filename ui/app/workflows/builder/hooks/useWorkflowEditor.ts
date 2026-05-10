// ui/app/workflows/builder/hooks/useWorkflowEditor.ts

'use client';

import { useState, useEffect } from 'react';
import { useCallback } from 'react';
import { type Step, type Connection } from '@/entities/workflow';
import { useRouter, useSearchParams } from 'next/navigation';
import { getWorkflow, createWorkflow } from '@/shared/api';
import { createStepIdFromName, validateDependencies } from '@/shared/lib/step-utils';
import { useToast } from '@/features/toast';

export interface WorkflowState {
  id: string;
  name: string;
  description: string;
  steps: Step[];
  connections: Connection[];
  status: string;
  trigger_type?: string;
  trigger_input_schema?: Record<string, any>;
}

export function useWorkflowEditor() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { toast } = useToast();

  const fromWorkflowId = searchParams.get('from_workflow');
  const nameParam = searchParams.get('name');
  const descriptionParam = searchParams.get('description');

  const emptyWorkflow: WorkflowState = {
    id: '',
    name: nameParam || 'New Workflow',
    description: descriptionParam || '',
    steps: [],
    connections: [],
    status: 'draft',
  };

  const [workflow, setWorkflow] = useState<WorkflowState>(emptyWorkflow);
  const [loading, setLoading] = useState(!!fromWorkflowId);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);

  // ---- helpers ----

  /**
   * Convert the steps field from an API response (object or array) to a Step array,
   * and derive an initial connections array from depends_on.
   */
  function normalizeStepsAndConnections(rawSteps: any): {
    steps: Step[];
    connections: Connection[];
  } {
    let stepsArray: Step[] = [];
    if (rawSteps) {
      if (Array.isArray(rawSteps)) {
        stepsArray = rawSteps;
      } else if (typeof rawSteps === 'object') {
        stepsArray = Object.entries(rawSteps).map(([id, config]: [string, any]) => ({
          id,
          ...(typeof config === 'object' && config !== null ? config : {}),
        })) as Step[];
      }
    }

    const connections: Connection[] = [];
    stepsArray.forEach((step: Step) => {
      if (step.depends_on && step.depends_on.length > 0) {
        step.depends_on.forEach((sourceId: string) => {
          connections.push({
            id: `conn-${sourceId}-${step.id}`,
            source: sourceId,
            target: step.id,
            source_id: sourceId,
            target_id: step.id,
          });
        });
      }
    });

    return { steps: stepsArray, connections };
  }

  // ---- data loading ----

  useEffect(() => {
    if (!fromWorkflowId) return;

    async function loadData() {
      try {
        setLoading(true);

        const fetched = await getWorkflow(fromWorkflowId!);
        const { steps, connections } = normalizeStepsAndConnections(fetched.steps);
        setWorkflow({
          id: '',
          name: nameParam || `Copy of ${fetched.name}`,
          description:
            descriptionParam !== null ? descriptionParam : fetched.description || '',
          steps,
          connections,
          status: 'draft',
        });

        setLoadError(null);
      } catch (error) {
        setLoadError(error instanceof Error ? error.message : 'Failed to load data');
      } finally {
        setLoading(false);
      }
    }

    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- nameParam/descriptionParam only needed on initial load
  }, [fromWorkflowId]);

  // ---- step CRUD ----

  const addStep = () => {
    const stepName = `New Step ${workflow.steps.length + 1}`;
    const stepId = createStepIdFromName(stepName, workflow.steps);

    const newStep: Step = {
      id: stepId,
      name: stepName,
      type: 'task',
      position: {
        x: 250,
        y: 300 + workflow.steps.length * 100,
      },
      parameters: {},
      outputs: {},
      input_mappings: {},
      depends_on: [],
    };

    setWorkflow(prev => ({ ...prev, steps: [...prev.steps, newStep] }));
    setSelectedStepId(newStep.id);
  };

  const updateStep = (updatedStep: Step) => {
    setWorkflow(prev => ({
      ...prev,
      steps: prev.steps.map((step: Step) =>
        step.id === updatedStep.id ? updatedStep : step
      ),
    }));
  };

  const handleStepsChange = useCallback((updatedSteps: Step[]) => {
    setWorkflow(prev => ({ ...prev, steps: updatedSteps }));
  }, []);

  const removeStep = (stepId: string) => {
    const cleanedSteps = workflow.steps
      .filter((step: Step) => step.id !== stepId)
      .map((step: Step) => {
        const cleanedDependsOn = step.depends_on?.filter(dep => dep !== stepId) || [];

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

        return { ...step, depends_on: cleanedDependsOn, input_mappings: cleanedInputMappings };
      });

    const cleanedConnections = workflow.connections.filter(
      (conn: Connection) => conn.source_id !== stepId && conn.target_id !== stepId
    );

    setWorkflow(prev => ({ ...prev, steps: cleanedSteps, connections: cleanedConnections }));

    if (selectedStepId === stepId) {
      setSelectedStepId(null);
    }
  };

  const duplicateStep = (selectedStep: Step) => {
    const duplicateStepName = `Copy of ${selectedStep.name}`;
    const duplicateStepId = createStepIdFromName(duplicateStepName, workflow.steps);

    const newStep: Step = {
      ...JSON.parse(JSON.stringify(selectedStep)),
      id: duplicateStepId,
      name: duplicateStepName,
      position: {
        x: (selectedStep.position?.x || 0) + 50,
        y: (selectedStep.position?.y || 0) + 50,
      },
      depends_on: [],
    };

    setWorkflow(prev => ({ ...prev, steps: [...prev.steps, newStep] }));
    setSelectedStepId(newStep.id);
  };

  // ---- property update ----

  const handleWorkflowPropertyChange = (property: string, value: string) => {
    setWorkflow(prev => ({ ...prev, [property]: value }));
  };

  // ---- save / submit ----

  const saveWorkflow = async (e: React.FormEvent) => {
    e.preventDefault();

    // Sync depends_on from connections before saving
    const stepsWithDependencies = workflow.steps.map((step: Step) => {
      const incomingConnections = workflow.connections.filter(
        (conn: Connection) => conn.target_id === step.id
      );
      const depends_on = incomingConnections
        .map((conn: Connection) => conn.source_id)
        .filter((id): id is string => id !== '__instance_form__' && id !== undefined);

      return { ...step, depends_on: depends_on.length > 0 ? depends_on : [] };
    });

    // Convert steps array to record for validation
    const stepsRecord = stepsWithDependencies.reduce<Record<string, { depends_on?: string[] }>>(
      (acc, step) => {
        acc[step.id] = { depends_on: step.depends_on?.filter((d): d is string => d !== undefined) };
        return acc;
      },
      {}
    );

    const validation = validateDependencies(stepsRecord);
    if (!validation.valid) {
      toast({
        title: 'Cannot save workflow',
        description: validation.errors.join(', '),
        variant: 'destructive',
      });
      return;
    }

    setIsSubmitting(true);

    try {
      const stepsDict = stepsWithDependencies.reduce<Record<string, any>>((acc, step) => {
        const { id, position, ...stepData } = step;
        acc[id] = {
          ...stepData,
          depends_on: step.depends_on,
          ui_config: step.ui_config || (position ? { position } : undefined),
        };
        return acc;
      }, {});

      const workflowData: any = {
        name: workflow.name,
        description: workflow.description,
        status: workflow.status || 'draft',
        steps: stepsDict,
        scope: 'personal',
      };

      const savedWorkflow = await createWorkflow(workflowData);
      toast({ title: 'Workflow created', description: 'Workflow created successfully.', variant: 'success' });
      router.push(`/workflows/${savedWorkflow.id}/edit`);
    } catch (error: unknown) {
      toast({
        title: 'Failed to save workflow',
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return {
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
  };
}
