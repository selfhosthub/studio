// ui/app/workflows/[id]/edit/components/EventConfigSection.tsx

'use client';

import React, { useEffect, useState } from 'react';
import { getWorkflows, setWorkflowEventTrigger, clearWorkflowEventTrigger } from '@/shared/api';
import type { WorkflowResponse } from '@/shared/types/api';
import { useToast } from '@/features/toast';

type EventOn = 'completed' | 'failed' | 'terminal';

interface EventConfigSectionProps {
  workflowId: string;
  eventSourceWorkflowId: string | null;
  eventOn: EventOn | null;
  onSaved: (sourceWorkflowId: string, on: EventOn) => void;
  onCleared: () => void;
}

export function EventConfigSection({
  workflowId,
  eventSourceWorkflowId,
  eventOn,
  onSaved,
  onCleared,
}: EventConfigSectionProps) {
  const { toast } = useToast();

  const [workflows, setWorkflows] = useState<WorkflowResponse[]>([]);
  const [workflowsLoading, setWorkflowsLoading] = useState(true);
  const [sourceId, setSourceId] = useState<string>(eventSourceWorkflowId || '');
  const [on, setOn] = useState<EventOn>(eventOn || 'completed'); // defaults-ok
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const list = await getWorkflows();
        if (active) setWorkflows(list.filter((w) => w.id !== workflowId));
      } catch (err: unknown) {
        if (active) {
          toast({ title: 'Failed to load workflows', description: err instanceof Error ? err.message : String(err), variant: 'destructive' });
        }
      } finally {
        if (active) setWorkflowsLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [workflowId, toast]);

  const handleSave = async () => {
    if (!sourceId) {
      toast({ title: 'Select a source workflow', variant: 'destructive' });
      return;
    }
    setSaving(true);
    try {
      await setWorkflowEventTrigger(workflowId, { source_workflow_id: sourceId, on });
      onSaved(sourceId, on);
      toast({ title: 'Event trigger saved', variant: 'success' });
    } catch (err: unknown) {
      toast({ title: 'Failed to save event trigger', description: err instanceof Error ? err.message : String(err), variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async () => {
    if (!confirm('Remove the event trigger for this workflow?')) {
      return;
    }
    setSaving(true);
    try {
      await clearWorkflowEventTrigger(workflowId);
      setSourceId('');
      setOn('completed');
      onCleared();
      toast({ title: 'Event trigger removed', variant: 'success' });
    } catch (err: unknown) {
      toast({ title: 'Failed to remove event trigger', description: err instanceof Error ? err.message : String(err), variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="md:col-span-2 p-3 bg-surface rounded-md border border-primary">
      <div className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label htmlFor="event-source" className="form-label">
              Source workflow
            </label>
            <select
              id="event-source"
              value={sourceId}
              onChange={(e) => setSourceId(e.target.value)}
              disabled={workflowsLoading}
              className="form-select w-full mt-1"
            >
              <option value="">{workflowsLoading ? 'Loading...' : 'Select a workflow'}</option>
              {workflows.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
            <p className="form-helper">Run this workflow when the source reaches a state</p>
          </div>

          <div>
            <label htmlFor="event-on" className="form-label">
              On
            </label>
            <select
              id="event-on"
              value={on}
              onChange={(e) => setOn(e.target.value as EventOn)}
              className="form-select w-full mt-1"
            >
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="terminal">Either (completed or failed)</option>
            </select>
            <p className="form-helper">Which terminal state triggers this workflow</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="btn-primary text-xs px-3 py-1.5"
          >
            {saving ? 'Saving...' : 'Save event trigger'}
          </button>
          <button
            type="button"
            onClick={handleClear}
            disabled={saving}
            className="text-xs text-secondary hover:text-primary inline-flex items-center"
          >
            Remove event trigger
          </button>
        </div>
      </div>
    </div>
  );
}
