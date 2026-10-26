// ui/app/(authenticated)/workflows/[id]/edit/hooks/useUnsavedChanges.ts

import { useRef, useCallback, useEffect } from 'react';

interface UnsavedChangesState {
  workflow: any;
  webhookAuthType: string;
  webhookAuthHeaderValue: string;
  webhookJwtSecret: string;
}

type Snapshot = Record<string, any>;

// JSON with object keys sorted, so key order never reads as a change.
function stableStringify(value: unknown): string {
  return JSON.stringify(value, (_key, v) =>
    v && typeof v === 'object' && !Array.isArray(v)
      ? Object.keys(v).sort().reduce((acc: Record<string, unknown>, k) => { acc[k] = v[k]; return acc; }, {})
      : v
  );
}

function stepPosition(step: any): any {
  return step.ui_config?.position ?? step.position ?? null;
}

// Strip view-only fields; keep the canvas position unless the step had none when loaded.
function normalizeStep(step: any, unpositioned: Set<string>): any {
  const { ui_config, position, config, ...rest } = step;
  const { parameter_ui_state, ...dataConfig } = config ?? {};
  const normalized = Object.keys(dataConfig).length > 0 ? { ...rest, config: dataConfig } : rest;
  return unpositioned.has(step.id) ? normalized : { ...normalized, position: stepPosition(step) };
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
function normalizeStepDependsOn(steps: any[], connections: any[], unpositioned: Set<string>): any[] {
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
    ...normalizeStep(step, unpositioned),
    depends_on: dependsOnMap.get(step.id) ?? step.depends_on ?? [],
  }));
}

function buildStateSnapshot(state: UnsavedChangesState, unpositioned: Set<string>): Snapshot {
  const steps = state.workflow?.steps ?? [];
  const rawConnections = state.workflow?.connections ?? [];
  const connections = deriveConnectionsFromMappings(steps, rawConnections);
  return {
    name: state.workflow?.name,
    description: state.workflow?.description,
    status: state.workflow?.status,
    trigger_type: state.workflow?.trigger_type,
    steps: normalizeStepDependsOn(steps, connections, unpositioned),
    connections,
    webhook_method: state.workflow?.webhook_method,
    webhook_auth_type: state.webhookAuthType,
    webhook_auth_header_value: state.webhookAuthHeaderValue,
    webhook_jwt_secret: state.webhookJwtSecret,
  };
}

export function useUnsavedChanges(state: UnsavedChangesState) {
  const baselineRef = useRef<Snapshot | null>(null);
  const unpositionedRef = useRef<Set<string>>(new Set());

  const hasUnsavedChanges = useCallback(() => {
    if (!state.workflow || !baselineRef.current) return false;
    return stableStringify(buildStateSnapshot(state, unpositionedRef.current)) !== stableStringify(baselineRef.current);
  }, [state]);

  const markSaved = useCallback(() => {
    unpositionedRef.current = new Set();
    baselineRef.current = buildStateSnapshot(state, unpositionedRef.current);
  }, [state]);

  // Initialize saved state from loaded workflow data
  const markInitialState = useCallback((workflowData: any) => {
    const steps = workflowData.steps ?? [];
    unpositionedRef.current = new Set(steps.filter((step: any) => !stepPosition(step)).map((step: any) => step.id));
    baselineRef.current = buildStateSnapshot({
      workflow: workflowData,
      webhookAuthType: workflowData.webhook_auth_type || 'none',
      webhookAuthHeaderValue: workflowData.webhook_auth_header_value || '',
      webhookJwtSecret: workflowData.webhook_jwt_secret || '',
    }, unpositionedRef.current);
  }, []);

  // Absorb a step panel's materialized defaults into the baseline for fields the user has not changed.
  const rebaseStep = useCallback((prevStep: any, nextStep: any) => {
    const baseline = baselineRef.current;
    if (!baseline || !prevStep || prevStep.id !== nextStep.id) return;
    const index = baseline.steps.findIndex((step: any) => step.id === nextStep.id);
    if (index < 0) return;
    const unpositioned = unpositionedRef.current;
    const saved = baseline.steps[index];
    const prev = normalizeStep(prevStep, unpositioned);
    const next = normalizeStep(nextStep, unpositioned);
    const rebased = { ...saved };
    for (const key of new Set([...Object.keys(prev), ...Object.keys(next)])) {
      if (key === 'depends_on') continue;
      const changed = stableStringify(prev[key]) !== stableStringify(next[key]);
      if (!changed || stableStringify(saved[key]) !== stableStringify(prev[key])) continue;
      if (key in next) rebased[key] = next[key];
      else delete rebased[key];
    }
    baselineRef.current = { ...baseline, steps: baseline.steps.map((step: any, i: number) => (i === index ? rebased : step)) };
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

  return { hasUnsavedChanges, markSaved, markInitialState, rebaseStep };
}
