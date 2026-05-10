// ui/widgets/flow-editor/FlowEditor.tsx

'use client';

import React, { useCallback, useState, useEffect, useRef } from 'react';
import { ErrorBoundary } from '@/shared/ui';
import { usePreferences } from '@/entities/preferences';
import {
  ReactFlow,
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  ConnectionMode,
  Controls,
  ControlButton,
  ReactFlowProvider,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type OnConnect,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import {
  EMPTY_STRING_ARRAY,
  getDefaultEdgeOptions,
  ICON_STYLE_DEFAULT,
  ICON_STYLE_ACTIVE,
  ACTIVE_BUTTON_STYLE,
  DISABLED_BUTTON_STYLE,
  FIT_VIEW_DURATION,
  DEFAULT_NODE_X,
  DEFAULT_NODE_Y,
} from './constants';
import type {
  Step,
  FlexibleConnection,
  FlowEditorProps,
  CustomNodeData,
} from './types';
import CustomNode from './CustomNode';
import { edgeTypes as edgeTypesBase } from './CustomEdge';
import { useFlowHistory } from './hooks/useFlowHistory';
import { useAutoLayout } from './hooks/useAutoLayout';
import { useFlowNodeManager } from './hooks/useFlowNodeManager';
import { useFlowEdgeManager } from './hooks/useFlowEdgeManager';
import { useFlowLayout } from './hooks/useFlowLayout';
import { TIMEOUTS } from '@/shared/lib/constants';

// Re-export types for external consumers
export type { Step, FlexibleConnection, FlowEditorProps, CustomNodeData } from './types';
export type { WorkflowConnection } from './types';

// Define node/edge types as module-level constants to avoid React Flow warnings
// These must be defined outside of any component to maintain stable references
const nodeTypes = { customNode: CustomNode };
const edgeTypes = edgeTypesBase;

// The main FlowEditor component wrapped in ReactFlowProvider
export const FlowEditorWithProvider = (props: FlowEditorProps) => {
  return (
    <ErrorBoundary name="Flow Editor">
      <ReactFlowProvider>
        <FlowEditor {...props} />
      </ReactFlowProvider>
    </ErrorBoundary>
  );
};

// The main FlowEditor component
const FlowEditor = ({
  steps,
  connections,
  onStepsChange,
  onConnectionsChange,
  onStepSelect,
  selectedStepId,
  readOnly = false,
  className = '',
  fullscreen = false,
  onFitViewRef,
  onAutoArrangeRef,
  onAddStep,
  onToggleSettings,
  onToggleFullscreen,
  showSettingsActive = false,
  credentialIssueStepIds = EMPTY_STRING_ARRAY,
}: FlowEditorProps) => {
  const { preferences } = usePreferences();

  // ---- Undo/redo history ----
  const { handleUndo, handleRedo, canUndo, canRedo } = useFlowHistory({
    steps,
    connections,
    onStepsChange,
    onConnectionsChange,
  });

  // ---- Auto-layout calculator ----
  const { calculateLayout } = useAutoLayout({
    connections,
    preferences: {
      nodeWidth: preferences.nodeWidth,
      nodeSpacing: preferences.nodeSpacing,
    },
  });

  // ---- Node management (Steps → ReactFlow nodes, handlers, field-mapping sync) ----
  const {
    stepsToNodes,
    syncInputMappingsToConnections,
    stableHandleStepDelete,
    stableHandleStepEdit,
    stableHandleStepToggleMode,
  } = useFlowNodeManager({
    steps,
    connections,
    selectedStepId,
    credentialIssueStepIds,
    nodeWidth: preferences.nodeWidth,
    onStepsChange,
    onConnectionsChange,
    onStepSelect,
  });

  // ---- Edge management (connections → ReactFlow edges, classify, delete) ----
  const {
    selectedEdgeId,
    setSelectedEdgeId,
    connectionsToEdges,
    handleEdgeDelete,
  } = useFlowEdgeManager({
    steps,
    connections,
    edgeStyle: preferences.edgeStyle,
    onConnectionsChange,
  });

  // ---- ReactFlow node/edge state ----
  const [nodes, setNodes] = useState<Node<CustomNodeData>[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  // Track whether we've done the initial layout and fit-view
  const hasInitializedLayoutRef = useRef(false);
  const hasFitViewRef = useRef(false);

  // ---- Layout / viewport / dark-mode (fit-view, auto-arrange, preference re-layout, mobile, dark) ----
  const { fitView } = useReactFlow();
  const isMobile =
    typeof window !== 'undefined' && window.innerWidth < 768;

  const { isInteractive, setIsInteractive, isDarkMode, autoArrangeFnRef } =
    useFlowLayout({
      steps,
      preferences: {
        nodeWidth: preferences.nodeWidth,
        nodeSpacing: preferences.nodeSpacing,
      },
      calculateLayout,
      onStepsChange,
      onFitViewRef,
      onAutoArrangeRef,
    });

  const gridColor = isDarkMode ? '#4b5563' : '#d1d5db'; // css-check-ignore: ReactFlow grid programmatic color

  // Call fitView once after initial nodes are placed
  useEffect(() => {
    if (!hasFitViewRef.current && nodes.length > 0) {
      hasFitViewRef.current = true;
      setTimeout(() => {
        fitView({ padding: isMobile ? 0.4 : 0.2, duration: FIT_VIEW_DURATION });
      }, TIMEOUTS.LAYOUT_SETTLE);
    }
  }, [nodes.length, fitView, isMobile]);

  // Sync steps → nodes (handles initial layout, additions, deletions, data updates)
  useEffect(() => {
    if (!hasInitializedLayoutRef.current) {
      hasInitializedLayoutRef.current = true;
      const stepsWithPositions = steps.every(
        step => step.ui_config?.position || step.position,
      )
        ? steps
        : calculateLayout(steps);

      if (stepsWithPositions !== steps && onStepsChange) {
        onStepsChange(stepsWithPositions);
      }

      setNodes(stepsToNodes(stepsWithPositions));
      setEdges(connectionsToEdges(connections));
      return;
    }

    // After initial layout, update nodes while preserving current positions
    setNodes(currentNodes => {
      const stepMap = new Map(steps.map(s => [s.id, s]));
      const currentNodeMap = new Map(currentNodes.map(n => [n.id, n]));

      const remainingNodes = currentNodes.filter(node => stepMap.has(node.id));

      const updatedNodes = remainingNodes.map(node => {
        const step = stepMap.get(node.id);
        if (!step) return node;

        const stepPosition = step.ui_config?.position || step.position;
        const newPosition = stepPosition ? stepPosition : node.position;

        return {
          ...node,
          position: newPosition,
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
            nodeWidth: preferences.nodeWidth,
            hasCredentialIssue: credentialIssueStepIds.includes(step.id),
            hasIteration: step.iteration_config?.enabled,
            iterationMode: step.iteration_config?.execution_mode,
          },
        };
      });

      const newSteps = steps.filter(step => !currentNodeMap.has(step.id));
      if (newSteps.length > 0) {
        const newNodes = newSteps.map(step => ({
          id: step.id,
          type: 'customNode' as const,
          position: step.ui_config?.position ||
            step.position || {
              x: DEFAULT_NODE_X + Math.random() * 200,
              y: DEFAULT_NODE_Y + Math.random() * 200,
            },
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
            nodeWidth: preferences.nodeWidth,
            hasCredentialIssue: credentialIssueStepIds.includes(step.id),
            hasIteration: step.iteration_config?.enabled,
            iterationMode: step.iteration_config?.execution_mode,
          },
        }));
        return [...updatedNodes, ...newNodes];
      }

      return updatedNodes;
    });

    // Auto-create connections from field mappings
    syncInputMappingsToConnections();
  }, [
    steps,
    stepsToNodes,
    selectedStepId,
    connections,
    preferences.nodeWidth,
    credentialIssueStepIds,
    calculateLayout,
    onStepsChange,
    stableHandleStepDelete,
    stableHandleStepEdit,
    stableHandleStepToggleMode,
    connectionsToEdges,
    syncInputMappingsToConnections,
  ]);

  // Sync connections → edges
  useEffect(() => {
    setEdges(connectionsToEdges(connections));
  }, [connections, connectionsToEdges]);

  // ---- Position tracking for drag operations ----
  const [pendingPositionChanges, setPendingPositionChanges] = useState<
    Record<string, { x: number; y: number }>
  >({});
  const isDraggingRef = useRef(false);

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const filteredChanges = changes.filter(change => change.type !== 'select');
      const newNodes = applyNodeChanges(filteredChanges, nodes) as Node<CustomNodeData>[];
      setNodes(newNodes);

      const positionChanges = changes.filter(
        change => change.type === 'position',
      ) as {
        type: 'position';
        id: string;
        position?: { x: number; y: number };
        dragging?: boolean;
      }[];

      if (positionChanges.length > 0) {
        const isDragInProgress = positionChanges.some(change => change.dragging);

        if (isDragInProgress) {
          isDraggingRef.current = true;
          const newPendingChanges = { ...pendingPositionChanges };
          positionChanges.forEach(change => {
            if (change.position) {
              newPendingChanges[change.id] = change.position;
            }
          });
          setPendingPositionChanges(newPendingChanges);
        } else if (isDraggingRef.current) {
          isDraggingRef.current = false;

          if (onStepsChange) {
            const updatedSteps = steps.map(step => {
              const position = pendingPositionChanges[step.id];
              if (position) {
                return { ...step, ui_config: { ...(step.ui_config || {}), position } };
              }
              return step;
            });
            onStepsChange(updatedSteps);
          }

          setPendingPositionChanges({});
        } else {
          if (onStepsChange) {
            const updatedSteps = steps.map(step => {
              const change = positionChanges.find(c => c.id === step.id);
              if (change && change.position) {
                return {
                  ...step,
                  ui_config: { ...(step.ui_config || {}), position: change.position },
                };
              }
              return step;
            });
            onStepsChange(updatedSteps);
          }
        }
      }
    },
    [nodes, onStepsChange, steps, pendingPositionChanges],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      const selectChange = changes.find(change => change.type === 'select') as
        | { type: 'select'; id: string; selected: boolean }
        | undefined;
      if (selectChange) {
        setSelectedEdgeId(selectChange.selected ? selectChange.id : null);
      }

      const newEdges = applyEdgeChanges(changes, edges);
      setEdges(newEdges);

      const removeChanges = changes.filter(change => change.type === 'remove');
      if (
        removeChanges.length > 0 &&
        onConnectionsChange &&
        connections &&
        connections.length > 0
      ) {
        const edgeIdsToRemove = new Set(removeChanges.map(c => c.id));

        const getConnectionId = (conn: FlexibleConnection) => {
          const sourceId = conn.source_id || conn.source || '';
          const targetId = conn.target_id || conn.target || '';
          return conn.id || `conn-${sourceId}-${targetId}`;
        };

        const updatedConnections = connections.filter(
          conn => !edgeIdsToRemove.has(getConnectionId(conn)),
        );

        if (selectedEdgeId && edgeIdsToRemove.has(selectedEdgeId)) {
          setSelectedEdgeId(null);
        }

        onConnectionsChange(updatedConnections);
      }
    },
    [edges, onConnectionsChange, connections, selectedEdgeId, setSelectedEdgeId],
  );

  // Stable ref for steps used in onConnect
  const stepsRef = useRef(steps);
  useEffect(() => {
    stepsRef.current = steps;
  }, [steps]);

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;

      const source = stepsRef.current.find(step => step.id === connection.source);
      const target = stepsRef.current.find(step => step.id === connection.target);

      if (source && target && onConnectionsChange) {
        const newConnection: FlexibleConnection = {
          id: `conn-${connection.source}-${connection.target}`,
          source_id: connection.source,
          target_id: connection.target,
        };
        onConnectionsChange([...connections, newConnection]);
      }
    },
    [onConnectionsChange, connections],
  );

  return (
    <div
      className={`w-full bg-card rounded-md ${className}`}
      style={fullscreen ? { height: '100%' } : { height: `${preferences.defaultEditorHeight}px` }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={!readOnly ? onNodesChange : undefined}
        onEdgesChange={!readOnly ? onEdgesChange : undefined}
        onConnect={!readOnly ? onConnect : undefined}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultEdgeOptions={getDefaultEdgeOptions(preferences.edgeStyle)}
        connectionMode={ConnectionMode.Strict}
        minZoom={0.2}
        maxZoom={4.0}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={isInteractive}
        nodesConnectable={isInteractive}
        elementsSelectable={isInteractive}
        panOnDrag={isInteractive}
        zoomOnScroll={isInteractive}
        zoomOnPinch={isInteractive}
        zoomOnDoubleClick={isInteractive}
        panOnScroll={false}
        preventScrolling={isInteractive}
      >
        <Controls
          showFitView={false}
          showZoom={true}
          showInteractive={false}
          position="top-left"
          style={
            isMobile
              ? { transform: 'scale(1.1)', transformOrigin: 'top left', marginTop: '4px', marginLeft: '4px' }
              : { transform: 'scale(1.5)', transformOrigin: 'top left' }
          }
        >
          {/* Add Step */}
          {onAddStep && !readOnly && (
            <ControlButton
              onClick={() => {
                onAddStep();
                setTimeout(
                  () =>
                    fitView({ padding: isMobile ? 0.4 : 0.2, duration: FIT_VIEW_DURATION }),
                  TIMEOUTS.LAYOUT_SETTLE,
                );
              }}
              title="Add Step"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                style={ICON_STYLE_DEFAULT}
              >
                <path
                  fillRule="evenodd"
                  d="M5.625 1.5H9a3.75 3.75 0 013.75 3.75v1.875c0 1.036.84 1.875 1.875 1.875H16.5a3.75 3.75 0 013.75 3.75v7.875c0 1.035-.84 1.875-1.875 1.875H5.625a1.875 1.875 0 01-1.875-1.875V3.375c0-1.036.84-1.875 1.875-1.875zM12.75 12a.75.75 0 00-1.5 0v2.25H9a.75.75 0 000 1.5h2.25V18a.75.75 0 001.5 0v-2.25H15a.75.75 0 000-1.5h-2.25V12z"
                  clipRule="evenodd"
                />
                <path d="M14.25 5.25a5.23 5.23 0 00-1.279-3.434 9.768 9.768 0 016.963 6.963A5.23 5.23 0 0016.5 7.5h-1.875a.375.375 0 01-.375-.375V5.25z" />
              </svg>
            </ControlButton>
          )}

          {/* Settings */}
          {onToggleSettings && (
            <ControlButton
              onClick={onToggleSettings}
              title="Editor Settings"
              style={showSettingsActive ? ACTIVE_BUTTON_STYLE : undefined}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                style={showSettingsActive ? ICON_STYLE_ACTIVE : ICON_STYLE_DEFAULT}
              >
                <path
                  fillRule="evenodd"
                  d="M11.078 2.25c-.917 0-1.699.663-1.85 1.567L9.05 4.889c-.02.12-.115.26-.297.348a7.493 7.493 0 00-.986.57c-.166.115-.334.126-.45.083L6.3 5.508a1.875 1.875 0 00-2.282.819l-.922 1.597a1.875 1.875 0 00.432 2.385l.84.692c.095.078.17.229.154.43a7.598 7.598 0 000 1.139c.015.2-.059.352-.153.43l-.841.692a1.875 1.875 0 00-.432 2.385l.922 1.597a1.875 1.875 0 002.282.818l1.019-.382c.115-.043.283-.031.45.082.312.214.641.405.985.57.182.088.277.228.297.35l.178 1.071c.151.904.933 1.567 1.85 1.567h1.844c.916 0 1.699-.663 1.85-1.567l.178-1.072c.02-.12.114-.26.297-.349.344-.165.673-.356.985-.57.167-.114.335-.125.45-.082l1.02.382a1.875 1.875 0 002.28-.819l.923-1.597a1.875 1.875 0 00-.432-2.385l-.84-.692c-.095-.078-.17-.229-.154-.43a7.614 7.614 0 000-1.139c-.016-.2.059-.352.153-.43l.84-.692c.708-.582.891-1.59.433-2.385l-.922-1.597a1.875 1.875 0 00-2.282-.818l-1.02.382c-.114.043-.282.031-.449-.083a7.49 7.49 0 00-.985-.57c-.183-.087-.277-.227-.297-.348l-.179-1.072a1.875 1.875 0 00-1.85-1.567h-1.843zM12 15.75a3.75 3.75 0 100-7.5 3.75 3.75 0 000 7.5z"
                  clipRule="evenodd"
                />
              </svg>
            </ControlButton>
          )}

          {/* Fit View */}
          <ControlButton
            onClick={() =>
              fitView({ padding: isMobile ? 0.4 : 0.2, duration: FIT_VIEW_DURATION })
            }
            title="Fit View"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              style={ICON_STYLE_DEFAULT}
            >
              <path
                fillRule="evenodd"
                d="M3 4.5A1.5 1.5 0 014.5 3h4.5a.75.75 0 010 1.5H4.5v4.5a.75.75 0 01-1.5 0V4.5zm16.5 0A1.5 1.5 0 0018 3h-4.5a.75.75 0 000 1.5H18v4.5a.75.75 0 001.5 0V4.5zM3 19.5A1.5 1.5 0 004.5 21h4.5a.75.75 0 000-1.5H4.5V15a.75.75 0 00-1.5 0v4.5zm16.5 0a1.5 1.5 0 01-1.5 1.5h-4.5a.75.75 0 010-1.5H18V15a.75.75 0 011.5 0v4.5z"
                clipRule="evenodd"
              />
            </svg>
          </ControlButton>

          {/* Auto-Arrange */}
          {!readOnly && (
            <ControlButton
              onClick={() => autoArrangeFnRef.current?.()}
              title="Auto-Arrange"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                style={ICON_STYLE_DEFAULT}
              >
                <path
                  fillRule="evenodd"
                  d="M3 6a3 3 0 013-3h2.25a3 3 0 013 3v2.25a3 3 0 01-3 3H6a3 3 0 01-3-3V6zm9.75 0a3 3 0 013-3H18a3 3 0 013 3v2.25a3 3 0 01-3 3h-2.25a3 3 0 01-3-3V6zM3 15.75a3 3 0 013-3h2.25a3 3 0 013 3V18a3 3 0 01-3 3H6a3 3 0 01-3-3v-2.25zm9.75 0a3 3 0 013-3H18a3 3 0 013 3V18a3 3 0 01-3 3h-2.25a3 3 0 01-3-3v-2.25z"
                  clipRule="evenodd"
                />
              </svg>
            </ControlButton>
          )}

          {/* Undo */}
          {!readOnly && (
            <ControlButton
              onClick={handleUndo}
              title="Undo (Ctrl+Z)"
              style={!canUndo ? DISABLED_BUTTON_STYLE : undefined}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                style={ICON_STYLE_DEFAULT}
              >
                <path
                  fillRule="evenodd"
                  d="M9.53 2.47a.75.75 0 010 1.06L4.81 8.25H15a6.75 6.75 0 010 13.5h-3a.75.75 0 010-1.5h3a5.25 5.25 0 100-10.5H4.81l4.72 4.72a.75.75 0 11-1.06 1.06l-6-6a.75.75 0 010-1.06l6-6a.75.75 0 011.06 0z"
                  clipRule="evenodd"
                />
              </svg>
            </ControlButton>
          )}

          {/* Redo */}
          {!readOnly && (
            <ControlButton
              onClick={handleRedo}
              title="Redo (Ctrl+Shift+Z)"
              style={!canRedo ? DISABLED_BUTTON_STYLE : undefined}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                style={ICON_STYLE_DEFAULT}
              >
                <path
                  fillRule="evenodd"
                  d="M14.47 2.47a.75.75 0 011.06 0l6 6a.75.75 0 010 1.06l-6 6a.75.75 0 11-1.06-1.06l4.72-4.72H9a5.25 5.25 0 100 10.5h3a.75.75 0 010 1.5H9a6.75 6.75 0 010-13.5h10.19l-4.72-4.72a.75.75 0 010-1.06z"
                  clipRule="evenodd"
                />
              </svg>
            </ControlButton>
          )}

          {/* Fullscreen */}
          {onToggleFullscreen && (
            <ControlButton
              onClick={onToggleFullscreen}
              title={fullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
              style={fullscreen ? ACTIVE_BUTTON_STYLE : undefined}
            >
              {fullscreen ? (
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  style={ICON_STYLE_ACTIVE}
                >
                  <path
                    fillRule="evenodd"
                    d="M3.22 3.22a.75.75 0 011.06 0l3.97 3.97V4.5a.75.75 0 011.5 0V9a.75.75 0 01-.75.75H4.5a.75.75 0 010-1.5h2.69L3.22 4.28a.75.75 0 010-1.06zm17.56 0a.75.75 0 010 1.06l-3.97 3.97h2.69a.75.75 0 010 1.5H15a.75.75 0 01-.75-.75V4.5a.75.75 0 011.5 0v2.69l3.97-3.97a.75.75 0 011.06 0zM3.75 15a.75.75 0 01.75-.75H9a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-2.69l-3.97 3.97a.75.75 0 01-1.06-1.06l3.97-3.97H4.5a.75.75 0 01-.75-.75zm10.5 0a.75.75 0 01.75-.75h4.5a.75.75 0 010 1.5h-2.69l3.97 3.97a.75.75 0 11-1.06 1.06l-3.97-3.97v2.69a.75.75 0 01-1.5 0V15z"
                    clipRule="evenodd"
                  />
                </svg>
              ) : (
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  style={ICON_STYLE_DEFAULT}
                >
                  <path
                    fillRule="evenodd"
                    d="M15 3.75a.75.75 0 01.75-.75h4.5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0V5.56l-3.97 3.97a.75.75 0 11-1.06-1.06l3.97-3.97h-2.69a.75.75 0 01-.75-.75zm-12 0A.75.75 0 013.75 3h4.5a.75.75 0 010 1.5H5.56l3.97 3.97a.75.75 0 01-1.06 1.06L4.5 5.56v2.69a.75.75 0 01-1.5 0v-4.5zm11.47 11.78a.75.75 0 111.06-1.06l3.97 3.97v-2.69a.75.75 0 011.5 0v4.5a.75.75 0 01-.75.75h-4.5a.75.75 0 010-1.5h2.69l-3.97-3.97zm-4.94-1.06a.75.75 0 010 1.06L5.56 19.5h2.69a.75.75 0 010 1.5h-4.5a.75.75 0 01-.75-.75v-4.5a.75.75 0 011.5 0v2.69l3.97-3.97a.75.75 0 011.06 0z"
                    clipRule="evenodd"
                  />
                </svg>
              )}
            </ControlButton>
          )}

          {/* Toggle Interactivity */}
          <ControlButton
            onClick={() => setIsInteractive(!isInteractive)}
            title={isInteractive ? 'Disable Interactivity' : 'Enable Interactivity'}
            style={!isInteractive ? ACTIVE_BUTTON_STYLE : undefined}
          >
            {isInteractive ? (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                style={ICON_STYLE_DEFAULT}
              >
                <path d="M18 1.5c2.9 0 5.25 2.35 5.25 5.25v3.75a.75.75 0 01-1.5 0V6.75a3.75 3.75 0 10-7.5 0v3a3 3 0 013 3v6.75a3 3 0 01-3 3H3.75a3 3 0 01-3-3v-6.75a3 3 0 013-3h9v-3c0-2.9 2.35-5.25 5.25-5.25z" />
              </svg>
            ) : (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                style={ICON_STYLE_ACTIVE}
              >
                <path
                  fillRule="evenodd"
                  d="M12 1.5a5.25 5.25 0 00-5.25 5.25v3a3 3 0 00-3 3v6.75a3 3 0 003 3h10.5a3 3 0 003-3v-6.75a3 3 0 00-3-3v-3c0-2.9-2.35-5.25-5.25-5.25zm3.75 8.25v-3a3.75 3.75 0 10-7.5 0v3h7.5z"
                  clipRule="evenodd"
                />
              </svg>
            )}
          </ControlButton>
        </Controls>
        {preferences.showGrid && <Background color={gridColor} gap={16} size={1} style={{ zIndex: 0 }} />} {/* css-check-ignore: ReactFlow override */}
      </ReactFlow>
    </div>
  );
};

export default FlowEditorWithProvider;
