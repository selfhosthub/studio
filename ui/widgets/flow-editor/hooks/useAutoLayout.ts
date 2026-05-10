// ui/widgets/flow-editor/hooks/useAutoLayout.ts

import { useCallback } from 'react';
import {
  DEFAULT_GAP_BETWEEN_NODES,
  COMPACT_GAP,
  SPACIOUS_GAP,
  VERTICAL_GAP,
  TARGET_CENTER_Y,
  BASE_CURVE_CLEARANCE,
  PER_JUMP_OFFSET,
  DEFAULT_NODE_X
} from '../constants';
import type { Step, FlexibleConnection } from '../types';

interface LayoutPreferences {
  nodeWidth: 'narrow' | 'normal' | 'wide';
  nodeSpacing: 'compact' | 'normal' | 'spacious';
}

interface UseAutoLayoutProps {
  connections: FlexibleConnection[];
  preferences: LayoutPreferences;
}

/**
 * Estimates the height of a node based on its content
 */
const estimateNodeHeight = (step: Step, nodeWidthSetting: 'narrow' | 'normal' | 'wide'): number => {
  let nodeWidth = 200;
  if (nodeWidthSetting === 'narrow') nodeWidth = 160;
  else if (nodeWidthSetting === 'wide') nodeWidth = 280;

  const contentWidth = nodeWidth - 32; // px-4 padding
  const charsPerLine = Math.floor(contentWidth / 8);

  const baseHeight = 16; // padding
  const titleLines = Math.ceil((step.name?.length || 10) / charsPerLine);
  const titleHeight = titleLines * 24;
  const descLines = step.description ? Math.ceil(step.description.length / charsPerLine) : 0;
  const descHeight = descLines * 16;
  const typeHeight = 20;

  return baseHeight + titleHeight + descHeight + typeHeight;
};

/**
 * Hook to calculate automatic layout for workflow steps based on their dependencies.
 * Uses a level-based approach where nodes are positioned horizontally by their
 * depth in the dependency graph, and vertically centered at each level.
 */
export function useAutoLayout({ connections, preferences }: UseAutoLayoutProps) {
  const calculateLayout = useCallback((steps: Step[]): Step[] => {
    // Get actual node width based on preference
    let actualNodeWidth = 200; // normal default
    if (preferences.nodeWidth === 'narrow') {
      actualNodeWidth = 160;
    } else if (preferences.nodeWidth === 'wide') {
      actualNodeWidth = 280;
    }

    // Calculate spacing: node width + gap between nodes
    let gapBetweenNodes = DEFAULT_GAP_BETWEEN_NODES;
    if (preferences.nodeSpacing === 'compact') {
      gapBetweenNodes = COMPACT_GAP;
    } else if (preferences.nodeSpacing === 'spacious') {
      gapBetweenNodes = SPACIOUS_GAP;
    }

    const levelSpacing = actualNodeWidth + gapBetweenNodes;
    const verticalGap = VERTICAL_GAP;

    // Build a set of all step IDs that are part of any connection
    // Use both depends_on from steps AND the connections array
    const connectedStepIds = new Set<string>();

    // From step.depends_on
    steps.forEach(step => {
      if (step.depends_on && step.depends_on.length > 0) {
        connectedStepIds.add(step.id);
        step.depends_on.forEach(depId => connectedStepIds.add(depId));
      }
    });

    // From connections array (source_id and target_id)
    connections.forEach(conn => {
      if (conn.source_id) connectedStepIds.add(conn.source_id);
      if (conn.target_id) connectedStepIds.add(conn.target_id);
    });

    // Separate connected steps from orphan steps
    const connectedSteps = steps.filter(s => connectedStepIds.has(s.id));
    const orphanSteps = steps.filter(s => !connectedStepIds.has(s.id));

    // If all steps are orphans (no connections), spread them horizontally
    if (connectedSteps.length === 0 && steps.length > 0) {
      return steps.map((step, index) => ({
        ...step,
        ui_config: {
          ...(step.ui_config || {}),
          position: {
            x: DEFAULT_NODE_X + index * levelSpacing,
            y: TARGET_CENTER_Y
          }
        }
      }));
    }

    // Build a dependency map from BOTH step.depends_on AND connections array
    // This ensures UI-drawn connections are used for level calculation
    const dependencyMap: Record<string, string[]> = {};

    // Initialize from step.depends_on
    steps.forEach(step => {
      dependencyMap[step.id] = [...(step.depends_on || [])];
    });

    // Add dependencies from connections array (target depends on source)
    connections.forEach(conn => {
      if (conn.source_id && conn.target_id) {
        if (!dependencyMap[conn.target_id]) {
          dependencyMap[conn.target_id] = [];
        }
        if (!dependencyMap[conn.target_id].includes(conn.source_id)) {
          dependencyMap[conn.target_id].push(conn.source_id);
        }
      }
    });

    // Create a map of step IDs to their level in the graph (for connected steps only)
    const levels: Record<string, number> = {};
    const processed = new Set<string>();

    // Find root steps (connected steps with no dependencies based on merged dependency map)
    const roots = connectedSteps.filter(step => {
      const deps = dependencyMap[step.id] || [];
      return deps.length === 0;
    });

    // Assign level 0 to roots
    roots.forEach(root => {
      levels[root.id] = 0;
      processed.add(root.id);
    });

    // Helper to get level for a step based on its dependencies
    const calculateLevel = (stepId: string): number => {
      if (processed.has(stepId)) {
        return levels[stepId];
      }

      const deps = dependencyMap[stepId] || [];
      if (deps.length === 0) {
        levels[stepId] = 0;
        processed.add(stepId);
        return 0;
      }

      // Get the max level of dependencies and add 1
      const dependencyLevels = deps.map(depId => {
        if (!steps.find(s => s.id === depId)) return 0;
        return calculateLevel(depId);
      });

      const level = Math.max(...dependencyLevels) + 1;
      levels[stepId] = level;
      processed.add(stepId);
      return level;
    };

    // Calculate levels for all connected steps
    connectedSteps.forEach(step => {
      if (!processed.has(step.id)) {
        calculateLevel(step.id);
      }
    });

    // Find the max level among connected steps
    const maxLevel = Math.max(...Object.values(levels), 0);

    // Group connected steps by level
    const stepsByLevel: Record<number, Step[]> = {};
    connectedSteps.forEach(step => {
      const level = levels[step.id] || 0;
      if (!stepsByLevel[level]) {
        stepsByLevel[level] = [];
      }
      stepsByLevel[level].push(step);
    });

    // Simple positioning: center all nodes around a target Y
    // Each level gets stacked vertically, centered around the target Y
    const targetCenterY = TARGET_CENTER_Y;

    // Find "data jump" connections - connections that skip levels
    // These need special handling to avoid overlapping with intermediate steps
    const dataJumpConnections: Array<{ sourceLevel: number; targetLevel: number; sourceId: string; targetId: string }> = [];
    connections.forEach(conn => {
      const sourceId = conn.source_id || conn.source;
      const targetId = conn.target_id || conn.target;
      if (!sourceId || !targetId) return;
      const sourceLevel = levels[sourceId];
      const targetLevel = levels[targetId];
      if (sourceLevel !== undefined && targetLevel !== undefined && targetLevel > sourceLevel + 1) {
        dataJumpConnections.push({ sourceLevel, targetLevel, sourceId, targetId });
      }
    });

    // For each level, check if it's "in between" a data jump connection
    // If so, offset those steps vertically to avoid the connection line
    const levelNeedsOffset: Record<number, boolean> = {};
    dataJumpConnections.forEach(({ sourceLevel, targetLevel }) => {
      for (let lvl = sourceLevel + 1; lvl < targetLevel; lvl++) {
        levelNeedsOffset[lvl] = true;
      }
    });

    // Count how many data-jump connections pass through each level
    // Steps at levels with more passing connections need more offset
    const levelJumpCount: Record<number, number> = {};
    dataJumpConnections.forEach(({ sourceLevel, targetLevel }) => {
      for (let lvl = sourceLevel + 1; lvl < targetLevel; lvl++) {
        levelJumpCount[lvl] = (levelJumpCount[lvl] || 0) + 1;
      }
    });

    // First pass: position all nodes centered at each level
    const positionedSteps: Array<{ step: Step; position: { x: number; y: number } }> = [];

    connectedSteps.forEach(step => {
      const level = levels[step.id] || 0;
      const stepsAtThisLevel = stepsByLevel[level] || [step];
      const indexInLevel = stepsAtThisLevel.indexOf(step);
      const countAtLevel = stepsAtThisLevel.length;
      const height = estimateNodeHeight(step, preferences.nodeWidth);

      // Check if this level needs to be offset due to data-jump connections passing through
      const needsOffset = levelNeedsOffset[level];
      const jumpCount = levelJumpCount[level] || 0;

      // Calculate the vertical offset for data-jump paths
      // Bezier curves arc through the middle, so we need clearance
      // More jump connections = more offset needed to create routing channels
      const baseOffset = verticalGap + BASE_CURVE_CLEARANCE;
      const perJumpOffset = PER_JUMP_OFFSET;
      const dataJumpOffset = baseOffset + (jumpCount > 1 ? (jumpCount - 1) * perJumpOffset : 0);

      let y: number;
      if (countAtLevel === 1) {
        // Single step - center it vertically (adjust for node height)
        y = targetCenterY - height / 2;
        // If this level is in the path of a data-jump, offset it UP to clear the connection lines
        // Connection lines pass through the center, so push nodes above the center line
        if (needsOffset) {
          y = targetCenterY - dataJumpOffset - height; // Position above the connection line path
        }
      } else {
        // Multiple steps - stack them centered around targetCenterY
        const heights = stepsAtThisLevel.map(s => estimateNodeHeight(s, preferences.nodeWidth));
        const totalHeight = heights.reduce((sum, h) => sum + h, 0) + (countAtLevel - 1) * verticalGap;
        let startY = targetCenterY - totalHeight / 2;
        // If this level needs offset, shift all steps UP to clear connection lines
        if (needsOffset) {
          startY = targetCenterY - dataJumpOffset - totalHeight;
        }

        // Sum up heights of nodes before this one
        for (let i = 0; i < indexInLevel; i++) {
          startY += heights[i] + verticalGap;
        }
        y = startY;
      }

      positionedSteps.push({
        step,
        position: { x: DEFAULT_NODE_X + level * levelSpacing, y }
      });
    });

    // Convert to updated steps
    const updatedSteps: Step[] = positionedSteps.map(({ step, position }) => ({
      ...step,
      ui_config: {
        ...(step.ui_config || {}),
        position
      }
    }));

    // Position orphan steps in a column after the last connected level
    const orphanLevel = maxLevel + 1;
    const orphanX = DEFAULT_NODE_X + orphanLevel * levelSpacing;

    // Orphan positioning - center around the same targetCenterY
    const orphanCount = orphanSteps.length;
    if (orphanCount > 0) {
      const orphanHeights = orphanSteps.map(s => estimateNodeHeight(s, preferences.nodeWidth));

      if (orphanCount === 1) {
        updatedSteps.push({
          ...orphanSteps[0],
          ui_config: {
            ...(orphanSteps[0].ui_config || {}),
            position: { x: orphanX, y: targetCenterY }
          }
        });
      } else {
        const totalHeight = orphanHeights.reduce((sum, h) => sum + h, 0) + (orphanCount - 1) * verticalGap;
        let currentY = targetCenterY - totalHeight / 2;

        orphanSteps.forEach((step, index) => {
          updatedSteps.push({
            ...step,
            ui_config: {
              ...(step.ui_config || {}),
              position: { x: orphanX, y: currentY }
            }
          });
          currentY += orphanHeights[index] + verticalGap;
        });
      }
    }

    return updatedSteps;
  }, [connections, preferences.nodeWidth, preferences.nodeSpacing]);

  return { calculateLayout };
}
