// ui/widgets/flow-editor/CustomNode.tsx

'use client';

import React from 'react';
import { Handle, Position, useReactFlow } from '@xyflow/react';
import { getStepTypeColor } from './constants';
import type { CustomNodeData } from './types';

interface CustomNodeProps {
  data: CustomNodeData;
  id: string;
}

/**
 * Custom node component for the workflow editor with:
 * - Delete, edit, and toggle mode buttons
 * - Execution mode visualization (enabled/skip/stop)
 * - Iteration badges
 * - Warning indicators
 */
const CustomNode = ({ data, id }: CustomNodeProps) => {
  const colors = getStepTypeColor(data.type);
  const { deleteElements } = useReactFlow();

  const handleDelete = (event: React.MouseEvent) => {
    event.stopPropagation();
    if (data.onDelete) {
      data.onDelete(id);
    } else {
      // Fallback to standard ReactFlow deletion if no custom handler
      deleteElements({ nodes: [{ id }] });
    }
  };

  const handleEdit = (event: React.MouseEvent) => {
    event.stopPropagation();
    if (data.onEdit) {
      data.onEdit(id);
    }
  };

  const handleToggleMode = (event: React.MouseEvent) => {
    event.stopPropagation();
    if (data.onToggleMode) {
      data.onToggleMode(id);
    }
  };

  // Get the next mode in the cycle: enabled -> skip -> stop -> enabled
  const getNextModeLabel = () => {
    switch (data.executionMode) {
      case 'skip': return 'Stop';
      case 'stop': return 'Enable';
      default: return 'Skip';
    }
  };

  // Get width class based on preference (narrow: 160px, normal: 200px, wide: 280px)
  const getWidthClass = () => {
    switch (data.nodeWidth) {
      case 'narrow':
        return 'w-[160px]';
      case 'wide':
        return 'w-[280px]';
      case 'normal':
      default:
        return 'w-[200px]';
    }
  };

  // Execution mode determines special styling
  const isSkipped = data.executionMode === 'skip';
  const isStopped = data.executionMode === 'stop';

  // Determine node styling based on state
  // Uses semantic flow-node-bg-* classes from globals.css for dark mode visibility
  const getNodeClasses = () => {
    // Skip mode: gray/muted appearance to show it's disabled
    if (isSkipped) {
      return 'border-gray-400 dark:border-gray-500 flow-node-bg-skip opacity-70'; // css-check-ignore -- step-type visualization borders
    }
    // Stop mode: red tint
    if (isStopped) {
      return 'border-red-400 dark:border-red-600 flow-node-bg-stop'; // css-check-ignore -- step-type visualization borders
    }
    if (data.isSelected) {
      return 'border-blue-500 flow-node-bg-selected'; // css-check-ignore -- step-type visualization border
    }
    if (data.hasCredentialIssue) {
      return 'border-amber-200 dark:border-amber-800 flow-node-bg-credential-issue hover:ring-2 hover:ring-amber-400 hover:ring-offset-1'; // css-check-ignore -- step-type visualization borders
    }
    return `${colors.border} ${colors.bg} flow-node-bg hover:ring-2 hover:ring-blue-400 hover:ring-offset-1`; // css-check-ignore -- step-type visualization
  };

  return (
    <div
      className={`group px-4 py-2 rounded-md shadow-md border-2 relative ${getWidthClass()} ${getNodeClasses()} transition-all duration-150`}
      style={{ wordWrap: 'break-word', overflowWrap: 'break-word' }}
    >
      {/* Skip mode: Dashed line through the step */}
      {isSkipped && (
        <div
          className="absolute inset-0 flex items-center justify-center pointer-events-none z-10"
          aria-hidden="true"
        >
          <div className="w-full border-t-2 border-dashed border-gray-500 dark:border-gray-400" /> {/* css-check-ignore -- step-type visualization */}
        </div>
      )}

      {/* Stop mode: Octagon stop sign at input connection point */}
      {isStopped && (
        <div
          className="absolute -left-3 top-1/2 -translate-y-1/2 w-6 h-6 flex items-center justify-center z-20"
          title="Workflow stops here"
        >
          {/* Octagon stop sign */}
          <svg
            viewBox="0 0 24 24"
            className="w-6 h-6"
            fill="currentColor"
          >
            <path
              className="text-danger"
              d="M7.86 2h8.28L22 7.86v8.28L16.14 22H7.86L2 16.14V7.86L7.86 2z"
            />
            <text
              x="12"
              y="16"
              textAnchor="middle"
              className="text-white"
              style={{ fontSize: '10px', fontWeight: 'bold' }}
            >
              ⏹
            </text>
          </svg>
        </div>
      )}

      {/* Source handle - where connections start from */}
      <Handle
        type="source"
        position={Position.Right}
        className={`!border-2 !border-white !w-3 !h-3 ${ // css-check-ignore -- ReactFlow handle overrides
          isSkipped ? '!bg-gray-400' : isStopped ? '!bg-red-500' : '!bg-blue-500' // css-check-ignore
        }`}
      />

      {/* Target handle - where connections end */}
      <Handle
        type="target"
        position={Position.Left}
        className={`!border-2 !border-white !w-3 !h-3 ${ // css-check-ignore -- ReactFlow handle overrides
          isSkipped ? '!bg-gray-400' : isStopped ? '!bg-red-500' : '!bg-blue-500' // css-check-ignore
        }`}
      />

      {/* Toggle mode button (top-left) - cycles through enabled -> skip -> stop */}
      <button
        type="button"
        onClick={handleToggleMode}
        className={`absolute -top-2 -left-2 rounded-full w-5 h-5 flex items-center justify-center shadow-sm transition-colors opacity-0 group-hover:opacity-100 pointer-coarse:opacity-100 data-[selected=true]:opacity-100 ${
          isSkipped
            ? 'bg-gray-400 hover:bg-gray-500 text-white' // css-check-ignore -- step-type visualization
            : isStopped
            ? 'bg-danger hover:bg-[var(--theme-danger)] text-white'
            : 'bg-gray-300 hover:bg-gray-400 text-gray-700' // css-check-ignore -- step-type visualization (fixed dark text on fixed light bg, not themed)
        }`}
        data-selected={data.isSelected}
        title={`Click to ${getNextModeLabel()}`}
      >
        {isSkipped ? (
          // Skip icon - forward arrow with line through
          <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 4l10 8-10 8V4z" />
            <line x1="19" y1="5" x2="19" y2="19" />
          </svg>
        ) : isStopped ? (
          // Stop icon - square
          <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="6" width="12" height="12" rx="1" />
          </svg>
        ) : (
          // Play/enabled icon - play triangle
          <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5v14l11-7z" />
          </svg>
        )}
      </button>

      {/* Edit/Settings button (top-center) - always visible on hover or when selected */}
      <button
        type="button"
        onClick={handleEdit}
        className="absolute -top-2 left-1/2 -translate-x-1/2 bg-info text-white rounded-full w-5 h-5 flex items-center justify-center shadow-sm hover:bg-[var(--theme-primary)] transition-colors opacity-0 group-hover:opacity-100 pointer-coarse:opacity-100 data-[selected=true]:opacity-100"
        data-selected={data.isSelected}
        title="Edit step settings"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-3 w-3"
          viewBox="0 0 24 24"
          fill="currentColor"
        >
          <path fillRule="evenodd" d="M11.078 2.25c-.917 0-1.699.663-1.85 1.567L9.05 4.889c-.02.12-.115.26-.297.348a7.493 7.493 0 00-.986.57c-.166.115-.334.126-.45.083L6.3 5.508a1.875 1.875 0 00-2.282.819l-.922 1.597a1.875 1.875 0 00.432 2.385l.84.692c.095.078.17.229.154.43a7.598 7.598 0 000 1.139c.015.2-.059.352-.153.43l-.841.692a1.875 1.875 0 00-.432 2.385l.922 1.597a1.875 1.875 0 002.282.818l1.019-.382c.115-.043.283-.031.45.082.312.214.641.405.985.57.182.088.277.228.297.35l.178 1.071c.151.904.933 1.567 1.85 1.567h1.844c.916 0 1.699-.663 1.85-1.567l.178-1.072c.02-.12.114-.26.297-.349.344-.165.673-.356.985-.57.167-.114.335-.125.45-.082l1.02.382a1.875 1.875 0 002.28-.819l.923-1.597a1.875 1.875 0 00-.432-2.385l-.84-.692c-.095-.078-.17-.229-.154-.43a7.614 7.614 0 000-1.139c-.016-.2.059-.352.153-.43l.84-.692c.708-.582.891-1.59.433-2.385l-.922-1.597a1.875 1.875 0 00-2.282-.818l-1.02.382c-.114.043-.282.031-.449-.083a7.49 7.49 0 00-.985-.57c-.183-.087-.277-.227-.297-.348l-.179-1.072a1.875 1.875 0 00-1.85-1.567h-1.843zM12 15.75a3.75 3.75 0 100-7.5 3.75 3.75 0 000 7.5z" clipRule="evenodd" />
        </svg>
      </button>

      {/* Delete button (top-right) - visible on hover or when selected */}
      <button
        type="button"
        onClick={handleDelete}
        className="absolute -top-2 -right-2 bg-danger text-white rounded-full w-5 h-5 flex items-center justify-center shadow-sm hover:bg-[var(--theme-danger)] transition-colors opacity-0 group-hover:opacity-100 pointer-coarse:opacity-100 data-[selected=true]:opacity-100"
        data-selected={data.isSelected}
        title="Delete step"
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

      <div className={`font-medium break-words ${isSkipped ? 'text-secondary' : isStopped ? 'text-danger' : 'text-primary'}`}>
        {data.label}
      </div>

      {data.description && (
        <div className={`text-xs break-words ${isSkipped ? 'text-muted dark:text-secondary' : isStopped ? 'text-danger' : 'text-secondary'}`}>
          {data.description}
        </div>
      )}

      {/* Execution mode badge */}
      {(isSkipped || isStopped) && (
        <div className={`text-xs mt-1 font-medium ${isSkipped ? 'text-secondary' : 'text-danger'}`}>
          {isSkipped ? 'SKIP' : 'STOP'}
        </div>
      )}

      {data.type && !isSkipped && !isStopped && (
        <div className={`text-xs ${colors.text} mt-1 font-medium`}>
          {data.type.charAt(0).toUpperCase() + data.type.slice(1)}
        </div>
      )}

      {/* Iteration badge */}
      {data.hasIteration && !isSkipped && !isStopped && (
        <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 bg-info text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full flex items-center gap-0.5 shadow-sm" title={`Iterating (${data.iterationMode || 'sequential'})`}>
          <svg xmlns="http://www.w3.org/2000/svg" className="h-2.5 w-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M17 2l4 4-4 4" />
            <path d="M3 11v-1a4 4 0 014-4h14" />
            <path d="M7 22l-4-4 4-4" />
            <path d="M21 13v1a4 4 0 01-4 4H3" />
          </svg>
          <span>{data.iterationMode === 'parallel' ? '∥' : '→'}</span>
        </div>
      )}

      {data.warnings && Object.keys(data.warnings).length > 0 && (
        <div className="mt-1 text-warning text-xs flex items-center">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            className="h-3 w-3 mr-1"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          {Object.keys(data.warnings).length} warning(s)
        </div>
      )}
    </div>
  );
};

export default React.memo(CustomNode);
