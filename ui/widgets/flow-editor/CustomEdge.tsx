// ui/widgets/flow-editor/CustomEdge.tsx

'use client';

import React from 'react';
import {
  EdgeLabelRenderer,
  getBezierPath,
  getSmoothStepPath,
  getStraightPath,
  type Edge,
  type EdgeProps,
} from '@xyflow/react';
import type { CustomEdgeData } from './types';

type CustomEdge = Edge<CustomEdgeData>;

/**
 * Delete button shown when an edge is selected
 */
const EdgeDeleteButton = ({
  labelX,
  labelY,
  id,
  onDelete
}: {
  labelX: number;
  labelY: number;
  id: string;
  onDelete?: (id: string) => void;
}) => (
  <EdgeLabelRenderer>
    <div
      style={{
        position: 'absolute',
        transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
        pointerEvents: 'all',
      }}
      className="nodrag nopan"
    >
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onDelete?.(id);
        }}
        className="bg-danger hover:bg-danger text-white rounded-full w-5 h-5 flex items-center justify-center shadow-md transition-colors"
        title="Delete connection"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-3 w-3"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>
    </div>
  </EdgeLabelRenderer>
);

type PathType = 'bezier' | 'straight' | 'smoothstep';

/**
 * Factory function to create custom edge components for different path types
 */
const createCustomEdge = (pathType: PathType) => {
  const CustomEdgeComponent = ({
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    style,
    markerEnd,
    selected,
    data
  }: EdgeProps<CustomEdge>) => {
    // Get path based on edge type
    let edgePath: string;
    let labelX: number;
    let labelY: number;

    if (pathType === 'straight') {
      [edgePath, labelX, labelY] = getStraightPath({ sourceX, sourceY, targetX, targetY });
    } else if (pathType === 'smoothstep') {
      [edgePath, labelX, labelY] = getSmoothStepPath({
        sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition
      });
    } else {
      // Default: bezier
      [edgePath, labelX, labelY] = getBezierPath({
        sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition
      });
    }

    return (
      <>
        <path
          id={id}
          style={style}
          className="react-flow__edge-path"
          d={edgePath}
          markerEnd={markerEnd}
        />
        {selected && (
          <EdgeDeleteButton
            labelX={labelX}
            labelY={labelY}
            id={id}
            onDelete={data?.onDelete}
          />
        )}
      </>
    );
  };

  CustomEdgeComponent.displayName = `CustomEdge_${pathType}`;
  return CustomEdgeComponent;
};

// Create edge components for each path type, memoized to skip re-renders
// when sibling edges change but this edge's props remain the same
export const CustomBezierEdge = React.memo(createCustomEdge('bezier'));
export const CustomStraightEdge = React.memo(createCustomEdge('straight'));
export const CustomSmoothStepEdge = React.memo(createCustomEdge('smoothstep'));

// Edge types object for ReactFlow
export const edgeTypes = {
  customBezier: CustomBezierEdge,
  customStraight: CustomStraightEdge,
  customSmoothStep: CustomSmoothStepEdge,
};
