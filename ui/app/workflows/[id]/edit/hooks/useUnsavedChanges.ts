// ui/app/workflows/[id]/edit/hooks/useUnsavedChanges.ts

import { useRef, useCallback, useEffect } from 'react';

interface UnsavedChangesState {
  workflow: any;
  webhookAuthType: string;
  webhookAuthHeaderValue: string;
  webhookJwtSecret: string;
}

// Strip canvas-only fields that mutate on mount without user interaction.
function normalizeStep(step: any): any {
  const { ui_config, position, ...rest } = step;
  return rest;
}

// Derive the connections that syncInputMappingsToConnections would auto-create from
// input_mappings. This mirrors the live FlowEditor behavior so the baseline snapshot
// matches the state the app converges to on mount - before any user interaction.
function deriveConnectionsFromMappings(steps: any[], existingConnections: any[]): any[] {
  const connectionMap = new Map<string, boolean>();
  existingConnections.forEach(conn => {
    const src = conn.source_id || conn.source;
    const tgt = conn.target_id || conn.target;
    if (src && tgt) connectionMap.set(`${src}:${tgt}`, true);
  });

  const result = [...existingConnections];
  steps.forEach(step => {
    const mappings = step.input_mappings || {};
    Object.values(mappings).forEach((mapping: any) => {
      if (mapping?.mappingType === 'mapped' && mapping?.stepId) {
        const key = `${mapping.stepId}:${step.id}`;
        if (!connectionMap.has(key)) {
          result.push({ id: `conn-${mapping.stepId}-${step.id}`, source_id: mapping.stepId, target_id: step.id });
          connectionMap.set(key, true);
        }
      }
    });
  });
  return result;
}

// Derive depends_on for each step from the normalized connection set, mirroring
// what syncStepWithConnections does when handleConnectionsChange fires on mount.
function normalizeStepDependsOn(steps: any[], connections: any[]): any[] {
  const dependsOnMap = new Map<string, string[]>();
  connections.forEach(conn => {
    const src = conn.source_id || conn.source;
    const tgt = conn.target_id || conn.target;
    if (src && tgt) {
      if (!dependsOnMap.has(tgt)) dependsOnMap.set(tgt, []);
      dependsOnMap.get(tgt)!.push(src);
    }
  });
  return steps.map(step => ({
    ...normalizeStep(step),
    depends_on: dependsOnMap.get(step.id) ?? step.depends_on ?? [],
  }));
}

function buildStateSnapshot(state: UnsavedChangesState): string {
  const steps = state.workflow?.steps ?? [];
  const rawConnections = state.workflow?.connections ?? [];
  const connections = deriveConnectionsFromMappings(steps, rawConnections);
  return JSON.stringify({
    name: state.workflow?.name,
    description: state.workflow?.description,
    status: state.workflow?.status,
    trigger_type: state.workflow?.trigger_type,
    steps: normalizeStepDependsOn(steps, connections),
    connections,
    webhook_method: state.workflow?.webhook_method,
    webhook_auth_type: state.webhookAuthType,
    webhook_auth_header_value: state.webhookAuthHeaderValue,
    webhook_jwt_secret: state.webhookJwtSecret,
  });
}

export function useUnsavedChanges(state: UnsavedChangesState) {
  const lastSavedStateRef = useRef<string>('');

  const hasUnsavedChanges = useCallback(() => {
    if (!state.workflow || !lastSavedStateRef.current) return false;
    return buildStateSnapshot(state) !== lastSavedStateRef.current;
  }, [state]);

  const markSaved = useCallback(() => {
    lastSavedStateRef.current = buildStateSnapshot(state);
  }, [state]);

  // Initialize saved state from loaded workflow data
  const markInitialState = useCallback((workflowData: any) => {
    const steps = workflowData.steps ?? [];
    const rawConnections = workflowData.connections ?? [];
    const connections = deriveConnectionsFromMappings(steps, rawConnections);
    lastSavedStateRef.current = JSON.stringify({
      name: workflowData.name,
      description: workflowData.description,
      status: workflowData.status,
      trigger_type: workflowData.trigger_type,
      steps: normalizeStepDependsOn(steps, connections),
      connections,
      webhook_method: workflowData.webhook_method,
      webhook_auth_type: workflowData.webhook_auth_type || 'none',
      webhook_auth_header_value: workflowData.webhook_auth_header_value || '',
      webhook_jwt_secret: workflowData.webhook_jwt_secret || '',
    });
  }, []);

  // Warn on browser close/refresh if there are unsaved changes
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges()) {
        e.preventDefault();
        e.returnValue = '';
        return '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [hasUnsavedChanges]);

  return { hasUnsavedChanges, markSaved, markInitialState };
}
