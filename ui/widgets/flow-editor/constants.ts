// ui/widgets/flow-editor/constants.ts

// Constants for the FlowEditor component

import { MarkerType } from '@xyflow/react';
import type { StepTypeColors } from './types';

// ======== LAYOUT CONSTANTS ========
export const MOBILE_BREAKPOINT = 768;
export const MOBILE_HEIGHT_THRESHOLD = 500;
export const DEFAULT_GAP_BETWEEN_NODES = 100;
export const COMPACT_GAP = 50;
export const SPACIOUS_GAP = 150;
export const VERTICAL_GAP = 80;
export const TARGET_CENTER_Y = 200;
export const BASE_CURVE_CLEARANCE = 40;
export const PER_JUMP_OFFSET = 30;
export const DEFAULT_NODE_X = 100;
export const DEFAULT_NODE_Y = 100;

// ======== ANIMATION CONSTANTS ========
export const FIT_VIEW_DURATION = 200;

// ======== HISTORY CONSTANTS ========
export const MAX_HISTORY_ENTRIES = 50;
export const HISTORY_DEBOUNCE_MS = 100;

// ======== STABLE REFERENCES ========
// Stable empty array for default props (prevents re-renders from new array references)
export const EMPTY_STRING_ARRAY: string[] = [];

// ======== STEP TYPE COLORS ========
const STEP_TYPE_COLOR_MAP: Record<string, StepTypeColors> = {
  trigger: {
    bg: 'bg-success-subtle',
    text: 'text-success',
    border: 'border-success'
  },
  task: {
    bg: 'bg-info-subtle',
    text: 'text-info',
    border: 'border-info'
  },
  condition: {
    bg: 'bg-step-condition',
    text: 'text-step-condition',
    border: 'border-step-condition'
  },
  action: {
    bg: 'bg-step-action',
    text: 'text-step-action',
    border: 'border-step-action'
  },
  notification: {
    bg: 'bg-step-notification',
    text: 'text-step-notification',
    border: 'border-step-notification'
  },
  webhook: {
    bg: 'bg-step-webhook',
    text: 'text-step-webhook',
    border: 'border-step-webhook'
  },
  decision: {
    bg: 'bg-step-decision',
    text: 'text-warning',
    border: 'border-step-decision'
  },
  approval: {
    bg: 'bg-step-approval',
    text: 'text-step-approval',
    border: 'border-step-approval'
  },
};

const DEFAULT_STEP_TYPE_COLORS: StepTypeColors = {
  bg: 'bg-card',
  text: 'text-primary',
  border: 'border-primary'
};

/**
 * Get step type colors for styling nodes (with dark mode support)
 */
export const getStepTypeColor = (type?: string): StepTypeColors => {
  if (!type) return DEFAULT_STEP_TYPE_COLORS;
  return STEP_TYPE_COLOR_MAP[type] ?? DEFAULT_STEP_TYPE_COLORS;
};

// ======== EDGE STYLES ========
export const DEFAULT_EDGE_COLOR = '#3b82f6';
export const SELECTED_EDGE_COLOR = '#ef4444';

export const getDefaultEdgeOptions = (edgeStyle: string) => {
  let edgeType = 'default'; // bezier is default
  if (edgeStyle === 'straight') {
    edgeType = 'straight';
  } else if (edgeStyle === 'step') {
    edgeType = 'smoothstep';
  }

  return {
    style: { stroke: DEFAULT_EDGE_COLOR, strokeWidth: 8 },
    type: edgeType,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      width: 10,
      height: 10,
      color: DEFAULT_EDGE_COLOR,
    },
    animated: false,
  };
};

// Stable references for non-selected edge props (prevents object recreation per edge per render)
export const DEFAULT_EDGE_STYLE = { stroke: DEFAULT_EDGE_COLOR, strokeWidth: 4 };
export const DEFAULT_EDGE_MARKER_END = {
  type: MarkerType.ArrowClosed,
  width: 10,
  height: 10,
  color: DEFAULT_EDGE_COLOR,
};

export const getSelectedEdgeStyle = () => ({
  stroke: SELECTED_EDGE_COLOR,
  strokeWidth: 4,
});

export const getSelectedMarkerEnd = () => ({
  type: MarkerType.ArrowClosed,
  width: 10,
  height: 10,
  color: SELECTED_EDGE_COLOR,
});

// ======== TOOLBAR STYLES ========
// Extracted inline styles to prevent recreation on each render
export const TOOLBAR_STYLE_MOBILE = {
  transform: 'scale(1.1)',
  transformOrigin: 'top left',
  marginTop: '4px',
  marginLeft: '4px',
};

export const TOOLBAR_STYLE_DESKTOP = {
  transform: 'scale(1.5)',
  transformOrigin: 'top left',
};

export const ICON_STYLE_DEFAULT = { width: 16, height: 16, fill: 'currentColor' };
export const ICON_STYLE_ACTIVE = { width: 16, height: 16, fill: 'var(--theme-btn-primary-text)' };
export const ACTIVE_BUTTON_STYLE = { backgroundColor: 'var(--theme-primary)' };
export const DISABLED_BUTTON_STYLE = { opacity: 0.4, cursor: 'not-allowed' as const };
