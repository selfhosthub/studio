// ui/widgets/flow-editor/hooks/useFlowNodeManager.ts

import { useCallback, useEffect, useMemo, useRef } from 'react';
import type { Node } from '@xyflow/react';
import { DEFAULT_NODE_X, DEFAULT_NODE_Y } from '../constants';
import type { Step, FlexibleConnection, CustomNodeData } from '../types';

interface UseFlowNodeManagerProps {
  steps: Step[];
  connections: FlexibleConnection[];
  selectedStepId?: string | null;
  credentialIssueStepIds: string[];
  nodeWidth: 'narrow' | 'normal' | 'wide';
  onStepsChange?: (steps: Step[]) => void;
  onConnectionsChange?: (connections: FlexibleConnection[]) => void;
  onStepSelect?: (stepId: string | null) => void;
}

interface UseFlowNodeManagerReturn {
  stepsToNodes: (stepsArray: Step[]) => Node<CustomNodeData>[];
  syncInputMappingsToConnections: () => void;
  stableHandleStepDelete: (stepId: string) => void;
  stableHandleStepEdit: (stepId: string) => void;
  stableHandleStepToggleMode: (stepId: string) => void;
}

/**
 * Hook to manage conversion of Steps → ReactFlow nodes, step action handlers,
 * and field-mapping detection that auto-creates connections from input_mappings.
 */
export function useFlowNodeManager({
  steps,
  connections,
  selectedStepId,
  credentialIssueStepIds,
  nodeWidth,
  onStepsChange,
  onConnectionsChange,
  onStepSelect,
}: UseFlowNodeManagerProps): UseFlowNodeManagerReturn {
  // ---- Step action handlers ----

  const handleStepDelete = useCallback(
    (stepId: string) => {
      if (onStepsChange && steps) {
        const updatedSteps = steps.filter(step => step.id !== stepId);

        if (onConnectionsChange && connections) {
          const updatedConnections = connections.filter(
            conn => conn.source_id !== stepId && conn.target_id !== stepId,
          );
          onConnectionsChange(updatedConnections);
        }

        onStepsChange(updatedSteps);

        if (selectedStepId === stepId && onStepSelect) {
          onStepSelect(null);
        }
      }
    },
    [onStepsChange, onConnectionsChange, onStepSelect, steps, connections, selectedStepId],
  );

  const handleStepEdit = useCallback(
    (stepId: string) => {
      if (onStepSelect) {
        onStepSelect(stepId);
      }
    },
    [onStepSelect],
  );

  const handleStepToggleMode = useCallback(
    (stepId: string) => {
      if (onStepsChange && steps) {
        const updatedSteps = steps.map(step => {
          if (step.id === stepId) {
            let newMode: 'enabled' | 'skip' | 'stop' | undefined;
            switch (step.execution_mode) {
              case 'skip':
                newMode = 'stop';
                break;
              case 'stop':
                newMode = undefined;
                break;
              default:
                newMode = 'skip';
            }
            return { ...step, execution_mode: newMode };
          }
          return step;
        });
        onStepsChange(updatedSteps);
      }
    },
    [onStepsChange, steps],
  );

  // Stable refs so stableHandle* callbacks never change identity
  const handleStepDeleteRef = useRef(handleStepDelete);
  const handleStepEditRef = useRef(handleStepEdit);
  const handleStepToggleModeRef = useRef(handleStepToggleMode);

  useEffect(() => {
    handleStepDeleteRef.current = handleStepDelete;
  }, [handleStepDelete]);

  useEffect(() => {
    handleStepEditRef.current = handleStepEdit;
  }, [handleStepEdit]);

  useEffect(() => {
    handleStepToggleModeRef.current = handleStepToggleMode;
  }, [handleStepToggleMode]);

  const stableHandleStepDelete = useCallback(
    (stepId: string) => handleStepDeleteRef.current(stepId),
    [],
  );
  const stableHandleStepEdit = useCallback(
    (stepId: string) => handleStepEditRef.current(stepId),
    [],
  );
  const stableHandleStepToggleMode = useCallback(
    (stepId: string) => handleStepToggleModeRef.current(stepId),
    [],
  );

  // ---- Steps → ReactFlow nodes ----

  const stepsToNodes = useMemo(() => {
    return (stepsArray: Step[]): Node<CustomNodeData>[] =>
      stepsArray.map(step => {
        const position =
          step.ui_config?.position || step.position || { x: DEFAULT_NODE_X, y: DEFAULT_NODE_Y };
        return {
          id: step.id,
          type: 'customNode',
          position,
          data: {
            label: step.name,
            description: step.description,
            type: step.type?.toLowerCase(),
            executionMode: step.execution_mode,
            serviceType: step.service_id,
            providerId: step.provider_id,
            serviceId: step.service_id,
            warnings: step.warnings,
            isSelected: selectedStepId === step.id,
            onDelete: stableHandleStepDelete,
            onEdit: stableHandleStepEdit,
            onToggleMode: stableHandleStepToggleMode,
            nodeWidth,
            hasCredentialIssue: credentialIssueStepIds.includes(step.id),
            hasIteration: step.iteration_config?.enabled,
            iterationMode: step.iteration_config?.execution_mode,
          },
        };
      });
  }, [
    selectedStepId,
    stableHandleStepDelete,
    stableHandleStepEdit,
    stableHandleStepToggleMode,
    nodeWidth,
    credentialIssueStepIds,
  ]);

  // ---- Field-mapping detection → auto-create connections ----

  const syncInputMappingsToConnections = useCallback(() => {
    if (!onConnectionsChange) return;

    const existingConnectionMap = new Map<string, boolean>();
    connections.forEach(conn => {
      const sourceId = conn.source_id || conn.source;
      const targetId = conn.target_id || conn.target;
      existingConnectionMap.set(`${sourceId}:${targetId}`, true);
    });

    const newConnections = [...connections];
    let hasNewConnections = false;

    steps.forEach(targetStep => {
      const inputMappings = targetStep.input_mappings || {};

      Object.values(inputMappings).forEach(mapping => {
        if (
          typeof mapping === 'object' &&
          (mapping as Record<string, unknown>).mappingType === 'mapped' &&
          (mapping as Record<string, unknown>).stepId
        ) {
          const sourceId = (mapping as Record<string, unknown>).stepId as string;
          const targetId = targetStep.id;
          const connectionKey = `${sourceId}:${targetId}`;

          if (!existingConnectionMap.has(connectionKey)) {
            hasNewConnections = true;
            newConnections.push({
              id: `conn-${sourceId}-${targetId}`,
              source_id: sourceId,
              target_id: targetId,
            });
            existingConnectionMap.set(connectionKey, true);
          }
        }
      });
    });

    if (hasNewConnections) {
      onConnectionsChange(newConnections);
    }
  }, [steps, connections, onConnectionsChange]);

  return {
    stepsToNodes,
    syncInputMappingsToConnections,
    stableHandleStepDelete,
    stableHandleStepEdit,
    stableHandleStepToggleMode,
  };
}
