// ui/widgets/flow-editor/types.ts

// Types and interfaces for the FlowEditor component

// Import canonical Step from entities layer and re-export
import type { Step } from '@/entities/workflow';
export type { Step };

/**
 * Represents a connection between workflow steps.
 * FlowEditor uses source_id/target_id internally.
 */
export interface WorkflowConnection {
  id: string;
  source_id: string;
  target_id: string;
}

/**
 * Flexible connection type for compatibility with existing code.
 * Accepts both source_id/target_id and source/target naming conventions.
 */
export interface FlexibleConnection {
  id: string;
  source_id?: string;
  target_id?: string;
  source?: string;
  target?: string;
}

/**
 * Custom node data passed to ReactFlow nodes
 */
export interface CustomNodeData extends Record<string, unknown> {
  label: string;
  description?: string;
  serviceType?: string;
  providerId?: string;
  serviceId?: string;
  warnings?: Record<string, unknown>;
  isSelected?: boolean;
  type?: string;
  executionMode?: 'enabled' | 'skip' | 'stop';
  onDelete?: (id: string) => void;
  onEdit?: (id: string) => void;
  onToggleMode?: (id: string) => void;
  nodeWidth?: 'narrow' | 'normal' | 'wide';
  hasCredentialIssue?: boolean;
  hasIteration?: boolean;
  iterationMode?: 'sequential' | 'parallel';
}

/**
 * Props for the FlowEditor component
 */
export interface FlowEditorProps {
  steps: Step[];
  connections: FlexibleConnection[];
  onStepsChange?: (steps: Step[]) => void;
  onConnectionsChange?: (connections: FlexibleConnection[]) => void;
  onStepSelect?: (stepId: string | null) => void;
  selectedStepId?: string | null;
  readOnly?: boolean;
  className?: string;
  /** When true, use 100% height instead of preference height */
  fullscreen?: boolean;
  /** Callback to expose fitView function */
  onFitViewRef?: (fitViewFn: () => void) => void;
  /** Callback to expose autoArrange function */
  onAutoArrangeRef?: (autoArrangeFn: () => void) => void;
  /** Toolbar action callbacks */
  onAddStep?: () => void;
  onToggleSettings?: () => void;
  onToggleFullscreen?: () => void;
  /** Whether settings panel is currently shown */
  showSettingsActive?: boolean;
  /** Mode: 'blueprint' skips field mapping modal, 'workflow' shows full mapping UI */
  mode?: 'blueprint' | 'workflow';
  /** Step IDs that have credential issues (shown with amber border) */
  credentialIssueStepIds?: string[];
}

/**
 * History state for undo/redo functionality
 */
export interface HistoryState {
  steps: Step[];
  connections: FlexibleConnection[];
}

/**
 * Custom edge data for ReactFlow edges
 */
export interface CustomEdgeData extends Record<string, unknown> {
  onDelete?: (edgeId: string) => void;
  edgeClass?: 'mapped' | 'unmapped';
}

/**
 * Step type color configuration
 */
export interface StepTypeColors {
  bg: string;
  text: string;
  border: string;
}
