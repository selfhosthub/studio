// ui/app/workflows/[id]/edit/components/SaveAsModal.tsx

'use client';

import React, { useState, useEffect } from 'react';
import { Modal } from '@/shared/ui';
import { createWorkflow } from '@/shared/api';
import { Step } from '@/entities/workflow';
import { useToast } from '@/features/toast';

interface SaveAsModalProps {
  isOpen: boolean;
  onClose: () => void;
  workflow: any;
  onSuccess: (newWorkflowId: string) => void;
}

export function SaveAsModal({ isOpen, onClose, workflow, onSuccess }: SaveAsModalProps) {
  const { toast } = useToast();
  const [saveAsName, setSaveAsName] = useState('');
  const [saveAsDescription, setSaveAsDescription] = useState('');
  const [isSavingAs, setIsSavingAs] = useState(false);

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen && workflow) {
      setSaveAsName(`${workflow.name} (Copy)`);
      setSaveAsDescription(workflow.description || '');
    }
  }, [isOpen, workflow]);

  const handleSaveAs = async () => {
    if (!workflow || !saveAsName.trim()) {
      toast({ title: 'Missing name', description: 'Please enter a name for the new workflow.', variant: 'destructive' });
      return;
    }

    setIsSavingAs(true);

    try {
      // Sync depends_on from connections before saving
      const connections = workflow.connections || [];
      const stepsWithDependencies = workflow.steps.map((step: Step) => {
        const incomingConnections = connections.filter((conn: any) => conn.target_id === step.id);
        const depends_on = incomingConnections.map((conn: any) => conn.source_id).filter((id: string) => id !== '__instance_form__');
        return { ...step, depends_on: depends_on.length > 0 ? depends_on : [] };
      });

      // Convert steps array to dictionary for backend
      const stepsDict = stepsWithDependencies.reduce((acc: Record<string, any>, step: Step) => {
        const { id, position, ...stepData } = step;
        const ui_config = step.ui_config || (position ? { position } : undefined);
        acc[id] = { ...stepData, depends_on: step.depends_on, ui_config };
        return acc;
      }, {});

      const newWorkflow = await createWorkflow({
        name: saveAsName.trim(),
        description: saveAsDescription.trim(),
        status: 'draft',
        trigger_type: workflow.trigger_type || 'manual',
        steps: stepsDict,
        scope: 'personal',
      });

      onClose();
      toast({ title: 'Workflow copied', description: 'Workflow saved as new copy successfully!', variant: 'success' });
      onSuccess(newWorkflow.id);
    } catch (error: unknown) {
      toast({ title: 'Failed to save copy', description: error instanceof Error ? error.message : 'Unknown error', variant: 'destructive' });
    } finally {
      setIsSavingAs(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Save Workflow As" size="sm">
      <div className="p-6">
        <div className="space-y-4">
          <div>
            <label htmlFor="save-as-name" className="form-label">
              Workflow Name
            </label>
            <input
              type="text"
              id="save-as-name"
              value={saveAsName}
              onChange={(e) => setSaveAsName(e.target.value)}
              className="form-input mt-1"
              placeholder="Enter workflow name"
              autoFocus
            />
          </div>

          <div>
            <label htmlFor="save-as-description" className="form-label">
              Description
            </label>
            <textarea
              id="save-as-description"
              rows={3}
              value={saveAsDescription}
              onChange={(e) => setSaveAsDescription(e.target.value)}
              className="form-textarea mt-1"
              placeholder="Enter workflow description"
            />
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="btn-secondary"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSaveAs}
            disabled={isSavingAs || !saveAsName.trim()}
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSavingAs ? 'Saving...' : 'Save as New Workflow'}
          </button>
        </div>
      </div>
    </Modal>
  );
}
