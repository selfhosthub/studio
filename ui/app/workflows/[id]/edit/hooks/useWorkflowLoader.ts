// ui/app/workflows/[id]/edit/hooks/useWorkflowLoader.ts

'use client';

import { useState, useEffect, useRef } from 'react';
import { Step } from '@/entities/workflow';
import { getWorkflow } from '@/shared/api';
import { topologicalSortSteps } from '@/shared/lib/step-utils';

interface UseWorkflowLoaderOptions {
  onLoaded?: (workflowData: any) => void;
}

/** Fetches a workflow, normalizes steps/connections format, and calls onLoaded after success. */
export function useWorkflowLoader(workflowId: string, options?: UseWorkflowLoaderOptions) {
  const [workflow, setWorkflow] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Ref prevents effect re-runs when the callback identity changes.
  const onLoadedRef = useRef(options?.onLoaded);
  onLoadedRef.current = options?.onLoaded;

  useEffect(() => {
    async function fetchWorkflow() {
      try {
        setLoading(true);
        const workflowData = await getWorkflow(workflowId);

        if (workflowData.steps && !Array.isArray(workflowData.steps)) {
          workflowData.steps = Object.entries(workflowData.steps).map(([id, config]: [string, any]) => ({
            id,
            ...(typeof config === 'object' && config !== null ? config : {})
          }));
        }

        if (!workflowData.steps) {
          workflowData.steps = [];
        }

        if (!workflowData.connections || workflowData.connections.length === 0) {
          const connections: any[] = [];
          workflowData.steps.forEach((step: Step) => {
            if (step.depends_on && step.depends_on.length > 0) {
              step.depends_on.forEach((sourceId: string) => {
                connections.push({
                  id: `conn-${sourceId}-${step.id}`,
                  source_id: sourceId,
                  target_id: step.id
                });
              });
            }
          });
          workflowData.connections = connections;
        } else {
          workflowData.steps = workflowData.steps.map((step: Step) => {
            const incomingConnections = workflowData.connections!.filter((conn: any) => conn.target_id === step.id);
            const depends_on = incomingConnections.map((conn: any) => conn.source_id);

            return {
              ...step,
              depends_on: depends_on.length > 0 ? depends_on : (step.depends_on || [])
            };
          });
        }

        workflowData.steps = topologicalSortSteps(workflowData.steps);

        setWorkflow(workflowData);
        onLoadedRef.current?.(workflowData);
        setError(null);
      } catch (err: unknown) {
        console.error('Failed to load workflow:', err);
        setError(err instanceof Error ? err.message : 'Failed to load workflow');
      } finally {
        setLoading(false);
      }
    }

    fetchWorkflow();
  }, [workflowId]);

  return { workflow, setWorkflow, loading, error };
}
