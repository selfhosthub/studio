// ui/widgets/flow-editor/AutomationCamera.tsx

'use client';

import { useEffect } from 'react';
import { useReactFlow } from '@xyflow/react';

const FIT_PADDING = 0.25;
const FIT_DURATION = 400;

declare global {
  interface Window {
    __STUDIO_AUTOMATION__?: { workflow?: WorkflowCamera };
  }
}

/** Camera commands a walkthrough runner calls by step id, so it never scrolls or drags the canvas. */
export interface WorkflowCamera {
  fitAll: () => Promise<boolean>;
  focusNode: (stepId: string) => Promise<boolean>;
  fitNodes: (stepIds: string[]) => Promise<boolean>;
  focusEdge: (sourceStepId: string, targetStepId: string) => Promise<boolean>;
  getNode: (stepId: string) => { id: string; x: number; y: number } | null;
  getViewport: () => { x: number; y: number; zoom: number };
}

/** Publishes the camera on window while the editor is mounted. Renders nothing. */
export function AutomationCamera() {
  const { fitView, getNode, getViewport } = useReactFlow();

  useEffect(() => {
    const fit = (nodes?: { id: string }[]) =>
      fitView({ nodes, padding: FIT_PADDING, duration: FIT_DURATION });

    const camera: WorkflowCamera = {
      fitAll: () => fit(),
      focusNode: (stepId) => fit([{ id: stepId }]),
      fitNodes: (stepIds) => fit(stepIds.map((id) => ({ id }))),
      focusEdge: (sourceStepId, targetStepId) =>
        fit([{ id: sourceStepId }, { id: targetStepId }]),
      getNode: (stepId) => {
        const node = getNode(stepId);
        return node ? { id: node.id, x: node.position.x, y: node.position.y } : null;
      },
      getViewport,
    };

    window.__STUDIO_AUTOMATION__ = { ...window.__STUDIO_AUTOMATION__, workflow: camera };
    return () => {
      delete window.__STUDIO_AUTOMATION__?.workflow;
    };
  }, [fitView, getNode, getViewport]);

  return null;
}

export default AutomationCamera;
