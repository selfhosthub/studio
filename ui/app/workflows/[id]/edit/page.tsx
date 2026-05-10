// ui/app/workflows/[id]/edit/page.tsx

'use client';

import React, { useState, use } from 'react';
import { Step } from '@/entities/workflow';
import Link from 'next/link';
import { validateDependencies, topologicalSortSteps } from '@/shared/lib/step-utils';
import { updateWorkflow, createInstance, exportWorkflow } from '@/shared/api';
import { useRouter } from 'next/navigation';
import { StepConfigPanel } from '@/widgets/flow-editor';
import { WorkflowStepConfig } from '@/app/workflows/components/WorkflowStepConfig';
import { usePreferences } from '@/entities/preferences';
import { useToast } from '@/features/toast';
import { TIMEOUTS } from '@/shared/lib/constants';

// Extracted hooks
import { useAutoSave } from './hooks/useAutoSave';
import { useUnsavedChanges } from './hooks/useUnsavedChanges';
import { useWebhookConfig } from './hooks/useWebhookConfig';
import { useCredentialCheck } from './hooks/useCredentialCheck';
import { useStepCRUD } from './hooks/useStepCRUD';
import { useConnectionSync } from './hooks/useConnectionSync';
import { useWorkflowLoader } from './hooks/useWorkflowLoader';

// Extracted components
import {
  SaveAsModal, WebhookAuthHelpModal,
  CredentialBanner, WorkflowSettingsCollapsible, WorkflowToolbar,
  FlowEditorSection, BottomActionBar,
} from './components';

export default function WorkflowEditPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { toast } = useToast();
  const { preferences } = usePreferences();
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [showSaveAsModal, setShowSaveAsModal] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  // Extracted hooks
  const { workflow, setWorkflow, loading, error } = useWorkflowLoader(id, {
    onLoaded: (data) => {
      webhook.initFromWorkflow(data);
      markInitialState(data);
    },
  });

  const webhook = useWebhookConfig(id, workflow?.webhook_token);
  const { credentialCheck, credentialCheckLoading, refreshCredentialCheck } = useCredentialCheck(workflow?.id);

  const { hasUnsavedChanges, markSaved, markInitialState } = useUnsavedChanges({
    workflow,
    webhookAuthType: webhook.webhookAuthType,
    webhookAuthHeaderValue: webhook.webhookAuthHeaderValue,
    webhookJwtSecret: webhook.webhookJwtSecret,
  });
  const steps = useStepCRUD(workflow, setWorkflow, selectedStepId, setSelectedStepId);
  const connections = useConnectionSync(workflow, setWorkflow, selectedStepId);

  // Handle workflow property updates
  const handleWorkflowPropertyChange = (property: string, value: string) => {
    if (!workflow) return;
    setWorkflow({ ...workflow, [property]: value });
  };

  // Handle trigger type change - called by WorkflowSettingsCollapsible after any confirmation
  const handleTriggerChange = async (newTriggerType: string) => {
    if (!workflow) return;

    // If switching away from webhook, delete the token first
    if (workflow.trigger_type === 'webhook' && workflow.webhook_token && newTriggerType !== 'webhook') {
      const success = await webhook.handleDeleteToken();
      if (success) {
        setWorkflow((prev: any) => ({ ...prev, webhook_token: null, webhook_secret: null, trigger_type: newTriggerType }));
      }
      return;
    }

    handleWorkflowPropertyChange('trigger_type', newTriggerType);

    // If switching to webhook, auto-generate token
    if (newTriggerType === 'webhook' && !workflow.webhook_token) {
      const result = await webhook.handleGenerateToken();
      if (result) {
        setWorkflow((prev: any) => ({ ...prev, webhook_token: result.webhook_token, webhook_secret: result.webhook_secret, trigger_type: 'webhook' }));
      } else {
        setWorkflow((prev: any) => ({ ...prev, trigger_type: 'manual' }));
      }
    }
  };

  const handleRegenerateWebhookToken = async () => {
    const result = await webhook.handleRegenerateToken();
    if (result) {
      setWorkflow((prev: any) => ({ ...prev, webhook_token: result.webhook_token, webhook_secret: result.webhook_secret }));
    }
  };

  const handleWebhookMethodChange = (method: 'POST' | 'GET') => {
    webhook.setWebhookMethod(method);
    if (workflow) setWorkflow({ ...workflow, webhook_method: method });
  };

  // Save workflow
  const saveWorkflow = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!workflow) {
      return;
    }

    // Sync depends_on from connections before saving
    const conns = workflow.connections || [];
    const stepsWithDependencies = workflow.steps.map((step: Step) => {
      const incoming = conns.filter((conn: any) => conn.target_id === step.id);
      const depends_on = incoming.map((conn: any) => conn.source_id).filter((id: string) => id !== '__instance_form__');
      return { ...step, depends_on: depends_on.length > 0 ? depends_on : [] };
    });

    // Validate dependencies
    const stepsRecord = stepsWithDependencies.reduce((acc: Record<string, any>, step: Step) => {
      acc[step.id] = step;
      return acc;
    }, {});
    const validation = validateDependencies(stepsRecord);
    if (!validation.valid) {
      toast({ title: 'Cannot save workflow', description: validation.errors.join(', '), variant: 'destructive' });
      return;
    }

    setIsSubmitting(true);

    try {
      // Sort steps topologically before serializing so dict key order reflects execution order
      const sortedSteps = topologicalSortSteps(stepsWithDependencies);

      // Convert steps array to dictionary for backend
      const stepsDict = sortedSteps.reduce((acc: Record<string, any>, step) => {
        const { id, ...stepData } = step;
        const position = (step as Record<string, unknown>).position;
        const ui_config = (step as Record<string, unknown>).ui_config || (position ? { position } : undefined);
        acc[id] = { ...stepData, depends_on: step.depends_on || [], ui_config };
        return acc;
      }, {});

      await updateWorkflow(workflow.id, {
        name: workflow.name,
        description: workflow.description,
        status: workflow.status,
        trigger_type: workflow.trigger_type,
        steps: stepsDict,
        webhook_method: workflow.webhook_method,
        webhook_auth_type: webhook.webhookAuthType,
        webhook_auth_header_name: webhook.webhookAuthType === 'header' ? 'X-API-Key' : null,
        webhook_auth_header_value: webhook.webhookAuthType === 'header' ? webhook.webhookAuthHeaderValue : null,
        webhook_jwt_secret: webhook.webhookAuthType === 'jwt' ? webhook.webhookJwtSecret : null,
      });

      await refreshCredentialCheck();
      markSaved();
      toast({ title: 'Workflow saved', description: 'Workflow saved successfully.', variant: 'success' });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), TIMEOUTS.MESSAGE_DISMISS);
    } catch (error: unknown) {
      toast({ title: 'Failed to save workflow', description: error instanceof Error ? error.message : 'Unknown error', variant: 'destructive' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const autoSave = useAutoSave({
    onSave: async () => { await saveWorkflow({ preventDefault: () => {} } as React.FormEvent); },
    hasUnsavedChanges,
  });

  const handleRun = async () => {
    if (!workflow) return;
    setIsRunning(true);
    try {
      const instance = await createInstance(workflow.id);
      router.push(`/instances/${instance.id}`);
    } catch (error: unknown) {
      toast({ title: 'Failed to run workflow', description: error instanceof Error ? error.message : 'Unknown error', variant: 'destructive' });
      setIsRunning(false);
    }
  };

  const handleExport = async () => {
    if (!workflow) return;
    setIsExporting(true);
    try {
      await exportWorkflow(workflow.id, workflow.name);
    } catch (error: unknown) {
      toast({ title: 'Failed to export workflow', description: error instanceof Error ? error.message : 'Unknown error', variant: 'destructive' });
    } finally {
      setIsExporting(false);
    }
  };

  const widthClass = {
    centered: 'max-w-5xl',
    wide: 'max-w-7xl',
    full: 'max-w-full'
  }[preferences.editorWidth];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <div className="spinner-lg"></div>
          <p className="mt-4 text-muted">Loading workflow...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="alert alert-error p-6">
          <h1 className="text-2xl font-bold text-danger mb-2">Error</h1>
          <p className="alert-error-text">{error}</p>
          <div className="mt-4">
            <Link href="/workflows/list" className="link">Back to workflow list</Link>
          </div>
        </div>
      </div>
    );
  }

  if (!workflow) {
    return (
      <div className="p-6">
        <div className="alert alert-warning p-6">
          <h1 className="text-2xl font-bold text-warning mb-2">Workflow Not Found</h1>
          <p className="alert-warning-text">The requested workflow could not be found.</p>
          <div className="mt-4">
            <Link href="/workflows/list" className="link">Back to workflow list</Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`p-2 ${widthClass} mx-auto`}>
      <WorkflowToolbar
        autoSave={autoSave}
        hasUnsavedChanges={hasUnsavedChanges()}
        isSubmitting={isSubmitting}
        isRunning={isRunning}
        hasSteps={!!workflow?.steps?.length}
        onSave={saveWorkflow}
        onRun={handleRun}
      />

      <form onSubmit={saveWorkflow}>
        <CredentialBanner
          credentialCheck={credentialCheck}
          credentialCheckLoading={credentialCheckLoading}
          onSelectStep={setSelectedStepId}
        />

        <WorkflowSettingsCollapsible
          workflow={workflow}
          webhook={webhook}
          onPropertyChange={handleWorkflowPropertyChange}
          onTriggerChange={handleTriggerChange}
          onMethodChange={handleWebhookMethodChange}
          onRegenerateToken={handleRegenerateWebhookToken}
        />

        <WebhookAuthHelpModal
          isOpen={webhook.showHmacHelpModal}
          onClose={() => webhook.setShowHmacHelpModal(false)}
        />

        <FlowEditorSection
          workflow={workflow}
          steps={steps}
          connections={connections}
          selectedStepId={selectedStepId}
          onStepSelect={setSelectedStepId}
          credentialIssueStepIds={credentialCheck?.issues?.map((i: any) => i.step_id) || []}
        />

        <StepConfigPanel
          isOpen={!!selectedStepId && !!steps.selectedStep}
          step={steps.selectedStep || null}
          onClose={() => setSelectedStepId(null)}
          previousSteps={connections.previousSteps}
          allSteps={steps.allStepsRecord}
          onSelectStep={setSelectedStepId}
          onSave={() => saveWorkflow({ preventDefault: () => {} } as React.FormEvent)}
          isSaving={isSubmitting}
          saveSuccess={saveSuccess}
          hasUnsavedChanges={hasUnsavedChanges()}
          autoSaveInterval={autoSave.autoSaveInterval}
          autoSaveCountdown={autoSave.autoSaveCountdown}
          onAutoSaveIntervalChange={autoSave.setAutoSaveInterval}
          onRun={handleRun}
          isRunning={isRunning}
          stepConfigContent={steps.selectedStep ? (
            <WorkflowStepConfig
              step={steps.selectedStep}
              onUpdate={steps.updateStep}
              onRemove={() => { steps.removeStep(steps.selectedStep!.id); setSelectedStepId(null); }}
              onDuplicate={steps.duplicateStep}
              previousSteps={connections.previousSteps}
              allSteps={steps.allStepsRecord}
              workflowId={id}
              onStepIdChange={steps.handleStepIdChange}
            />
          ) : null}
        />

        <BottomActionBar
          hasUnsavedChanges={hasUnsavedChanges()}
          isSubmitting={isSubmitting}
          isRunning={isRunning}
          isExporting={isExporting}
          hasSteps={!!workflow?.steps?.length}
          onRun={handleRun}
          onSaveAs={() => setShowSaveAsModal(true)}
          onExport={handleExport}
        />
      </form>

      <SaveAsModal
        isOpen={showSaveAsModal}
        onClose={() => setShowSaveAsModal(false)}
        workflow={workflow}
        onSuccess={(newId) => router.push(`/workflows/${newId}/edit`)}
      />
    </div>
  );
}
