// ui/widgets/flow-editor/index.ts

// Main components
export { default as FlowEditor, FlowEditorWithProvider } from './FlowEditor';
export { StepConfigPanel } from './StepConfigPanel';
export { EditorSettingsPanel } from './EditorSettingsPanel';
export { default as CustomNode } from './CustomNode';
export { CustomBezierEdge, CustomStraightEdge, CustomSmoothStepEdge, edgeTypes } from './CustomEdge';
export { default as ConfigureStepModal } from './ConfigureStepModal';
export { default as FormInputPanel } from './FormInputPanel';
export { default as WorkflowFormModal } from './WorkflowFormModal';

// Constants
export {
  MOBILE_BREAKPOINT,
  MOBILE_HEIGHT_THRESHOLD,
  DEFAULT_GAP_BETWEEN_NODES,
  COMPACT_GAP,
  SPACIOUS_GAP,
  VERTICAL_GAP,
  TARGET_CENTER_Y,
  BASE_CURVE_CLEARANCE,
  PER_JUMP_OFFSET,
  DEFAULT_NODE_X,
  DEFAULT_NODE_Y,
  MAX_HISTORY_ENTRIES,
  HISTORY_DEBOUNCE_MS,
  EMPTY_STRING_ARRAY,
  getStepTypeColor,
  DEFAULT_EDGE_COLOR,
  DEFAULT_EDGE_STYLE,
  DEFAULT_EDGE_MARKER_END,
  SELECTED_EDGE_COLOR,
  getDefaultEdgeOptions,
  getSelectedEdgeStyle,
  getSelectedMarkerEnd,
  TOOLBAR_STYLE_MOBILE,
  TOOLBAR_STYLE_DESKTOP,
  ICON_STYLE_DEFAULT,
  ICON_STYLE_ACTIVE,
  ACTIVE_BUTTON_STYLE,
  DISABLED_BUTTON_STYLE
} from './constants';

// Types
export type {
  WorkflowConnection,
  FlexibleConnection,
  Step,
  CustomNodeData,
  FlowEditorProps,
  HistoryState,
  CustomEdgeData,
  StepTypeColors
} from './types';

// Hooks
export { useFlowHistory } from './hooks/useFlowHistory';
export { useAutoLayout } from './hooks/useAutoLayout';
