// ui/widgets/flow-editor/hooks/useFlowEdgeManager.ts

import { useCallback, useMemo, useState } from 'react';
import type { Edge } from '@xyflow/react';
import {
  DEFAULT_EDGE_STYLE,
  DEFAULT_EDGE_MARKER_END,
  getSelectedEdgeStyle,
  getSelectedMarkerEnd,
} from '../constants';
import type { Step, FlexibleConnection } from '../types';

interface UseFlowEdgeManagerProps {
  steps: Step[];
  connections: FlexibleConnection[];
  edgeStyle: string;
  onConnectionsChange?: (connections: FlexibleConnection[]) => void;
}

interface UseFlowEdgeManagerReturn {
  selectedEdgeId: string | null;
  setSelectedEdgeId: (id: string | null) => void;
  connectionsToEdges: (conns: FlexibleConnection[]) => Edge[];
  handleEdgeDelete: (edgeId: string) => void;
  classifyEdge: (sourceId: string, targetId: string) => 'mapped' | 'unmapped';
}

/**
 * Hook to manage conversion of FlexibleConnections → ReactFlow edges,
 * edge classification (mapped vs unmapped), selected-edge tracking,
 * and edge deletion.
 */
export function useFlowEdgeManager({
  steps,
  connections,
  edgeStyle,
  onConnectionsChange,
}: UseFlowEdgeManagerProps): UseFlowEdgeManagerReturn {
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  // Determine if a target step has field mappings sourced from sourceId
  const hasFieldMappings = useCallback(
    (sourceId: string, targetId: string): boolean => {
      const targetStep = steps.find(s => s.id === targetId);
      if (!targetStep?.input_mappings) return false;

      for (const mapping of Object.values(targetStep.input_mappings)) {
        if (
          typeof mapping === 'object' &&
          (mapping as Record<string, unknown>).mappingType === 'mapped' &&
          (mapping as Record<string, unknown>).stepId === sourceId
        ) {
          return true;
        }
      }
      return false;
    },
    [steps],
  );

  const classifyEdge = useCallback(
    (sourceId: string, targetId: string): 'mapped' | 'unmapped' =>
      hasFieldMappings(sourceId, targetId) ? 'mapped' : 'unmapped',
    [hasFieldMappings],
  );

  const handleEdgeDelete = useCallback(
    (edgeId: string) => {
      if (onConnectionsChange && connections) {
        const updatedConnections = connections.filter(conn => conn.id !== edgeId);
        setSelectedEdgeId(null);
        onConnectionsChange(updatedConnections);
      }
    },
    [onConnectionsChange, connections],
  );

  const connectionsToEdges = useMemo(() => {
    return (conns: FlexibleConnection[]): Edge[] => {
      let edgeType = 'customBezier';
      if (edgeStyle === 'straight') {
        edgeType = 'customStraight';
      } else if (edgeStyle === 'step') {
        edgeType = 'customSmoothStep';
      }

      return conns
        .filter(connection => {
          const sourceId = connection.source_id || connection.source;
          const targetId = connection.target_id || connection.target;
          return sourceId && targetId;
        })
        .map(connection => {
          const sourceId = connection.source_id || connection.source || '';
          const targetId = connection.target_id || connection.target || '';
          const connectionId = connection.id || `conn-${sourceId}-${targetId}`;
          const isSelected = connectionId === selectedEdgeId;
          const edgeClass = classifyEdge(sourceId, targetId);

          return {
            id: connectionId,
            source: sourceId,
            target: targetId,
            type: edgeType,
            animated: false,
            zIndex: 1,
            style: isSelected ? getSelectedEdgeStyle() : DEFAULT_EDGE_STYLE,
            markerEnd: isSelected ? getSelectedMarkerEnd() : DEFAULT_EDGE_MARKER_END,
            selected: isSelected,
            data: {
              onDelete: handleEdgeDelete,
              edgeClass,
            },
          };
        });
    };
  }, [edgeStyle, selectedEdgeId, handleEdgeDelete, classifyEdge]);

  return {
    selectedEdgeId,
    setSelectedEdgeId,
    connectionsToEdges,
    handleEdgeDelete,
    classifyEdge,
  };
}
