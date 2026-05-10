// ui/entities/workflow/lib/step-position-utils.ts

// Pure utility functions for step positioning in the flow editor

import type { Step, Connection } from '../types';

/**
 * Estimate the rendered height of a step node based on its content.
 */
export function estimateStepHeight(step: Step, nodeWidth: number): number {
  const baseHeight = 16;
  const titleLineHeight = 24;
  const descLineHeight = 16;
  const typeHeight = 20;
  const contentWidth = nodeWidth - 32;
  const charsPerLine = Math.floor(contentWidth / 8);
  const titleLines = Math.ceil((step.name?.length || 10) / charsPerLine);
  const titleHeight = titleLines * titleLineHeight;
  let descHeight = 0;
  if (step.description) {
    const descLines = Math.ceil(step.description.length / charsPerLine);
    descHeight = descLines * descLineHeight;
  }
  return baseHeight + titleHeight + descHeight + typeHeight;
}

interface PositionPreferences {
  nodeWidth: 'narrow' | 'normal' | 'wide';
  nodeSpacing: 'compact' | 'normal' | 'spacious';
}

/**
 * Calculate the position for a new (unconnected) step, placing it in the
 * "orphan column" to the right of connected steps and below existing orphans.
 */
export function calculateNewStepPosition(
  existingSteps: Step[],
  connections: Connection[],
  preferences: PositionPreferences
): { x: number; y: number } {
  const defaultPosition = { x: 100, y: 200 };

  if (existingSteps.length === 0) {
    return defaultPosition;
  }

  // Resolve node width from preference
  let nodeWidth = 200;
  if (preferences.nodeWidth === 'narrow') nodeWidth = 160;
  else if (preferences.nodeWidth === 'wide') nodeWidth = 280;

  // Resolve gap from preference
  let gap = 100;
  if (preferences.nodeSpacing === 'compact') gap = 50;
  else if (preferences.nodeSpacing === 'spacious') gap = 150;

  const verticalGap = 30;

  // Build set of connected step IDs
  const connectedStepIds = new Set<string>();
  existingSteps.forEach((step: Step) => {
    if (step.depends_on && step.depends_on.length > 0) {
      connectedStepIds.add(step.id);
      step.depends_on.forEach((depId: string) => connectedStepIds.add(depId));
    }
  });
  connections.forEach((conn: Connection) => {
    if (conn.source_id) connectedStepIds.add(conn.source_id);
    if (conn.target_id) connectedStepIds.add(conn.target_id);
  });

  // Separate connected vs orphan steps
  const connectedSteps = existingSteps.filter((s: Step) => connectedStepIds.has(s.id));
  const orphanSteps = existingSteps.filter((s: Step) => !connectedStepIds.has(s.id));

  // Find X position: to the right of the rightmost connected step
  let orphanX = 100 + nodeWidth + gap;
  if (connectedSteps.length > 0) {
    const rightmostConnected = connectedSteps.reduce((rightmost: Step, step: Step) => {
      const stepX = step.ui_config?.position?.x || step.position?.x || 0;
      const rightmostX = rightmost.ui_config?.position?.x || rightmost.position?.x || 0;
      return stepX > rightmostX ? step : rightmost;
    }, connectedSteps[0]);
    const rightmostX = rightmostConnected.ui_config?.position?.x || rightmostConnected.position?.x || 100;
    orphanX = rightmostX + nodeWidth + gap;
  }

  // Find Y position: below the last orphan
  if (orphanSteps.length === 0) {
    return { x: orphanX, y: 200 };
  }

  let maxBottom = 0;
  orphanSteps.forEach((s: Step) => {
    const stepY = s.ui_config?.position?.y || s.position?.y || 200;
    const stepHeight = estimateStepHeight(s, nodeWidth);
    const bottom = stepY + stepHeight;
    if (bottom > maxBottom) maxBottom = bottom;
  });

  return { x: orphanX, y: maxBottom + verticalGap };
}
