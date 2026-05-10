// ui/app/workflows/[id]/edit/components/WorkflowSettingsCollapsible.tsx

'use client';

import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { WebhookConfigSection } from './WebhookConfigSection';
import { TriggerChangeModal } from './TriggerChangeModal';

interface WorkflowSettingsCollapsibleProps {
  workflow: any;
  webhook: any;
  onPropertyChange: (property: string, value: string) => void;
  onTriggerChange: (newTriggerType: string) => Promise<void>;
  onMethodChange: (method: 'POST' | 'GET') => void;
  onRegenerateToken: () => void;
}

export function WorkflowSettingsCollapsible({
  workflow,
  webhook,
  onPropertyChange,
  onTriggerChange,
  onMethodChange,
  onRegenerateToken,
}: WorkflowSettingsCollapsibleProps) {
  const [settingsExpanded, setSettingsExpanded] = useState<boolean>(() => {
    const saved = localStorage.getItem('globalWorkflowSettingsExpanded');
    return saved !== null ? saved === 'true' : true;
  });

  // Trigger change confirmation modal state
  const [showTriggerModal, setShowTriggerModal] = useState(false);
  const [pendingTriggerType, setPendingTriggerType] = useState<string | null>(null);

  useEffect(() => {
    localStorage.setItem('globalWorkflowSettingsExpanded', String(settingsExpanded));
  }, [settingsExpanded]);

  const handleTriggerSelect = (newTriggerType: string) => {
    // If switching away from webhook with an active token, confirm first
    if (workflow.trigger_type === 'webhook' && workflow.webhook_token && newTriggerType !== 'webhook') {
      setPendingTriggerType(newTriggerType);
      setShowTriggerModal(true);
    } else {
      onTriggerChange(newTriggerType);
    }
  };

  return (
    <>
      <div className={`shadow-sm rounded-lg mb-3 border ${
        settingsExpanded
          ? 'bg-card border-primary'
          : 'bg-surface border-secondary'
      }`}>
        <button
          type="button"
          onClick={() => setSettingsExpanded(!settingsExpanded)}
          className={`w-full px-3 py-3 flex items-center justify-between transition-colors rounded-t-lg ${
            settingsExpanded
              ? 'hover:bg-surface /50'
              : 'hover:bg-input'
          }`}
        >
          <h2 className="text-base font-medium text-primary">Workflow Settings</h2>
          {settingsExpanded ? (
            <ChevronUp className="h-5 w-5 text-muted" />
          ) : (
            <ChevronDown className="h-5 w-5 text-muted" />
          )}
        </button>
        {settingsExpanded && (
          <div className="px-3 pb-3 pt-2 border-t border-primary">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label htmlFor="workflow-name" className="form-label">
                  Workflow Name
                </label>
                <input
                  type="text"
                  id="workflow-name"
                  className="form-input mt-1"
                  value={workflow.name}
                  onChange={(e) => onPropertyChange('name', e.target.value)}
                  required
                />
              </div>

              <div>
                <label htmlFor="workflow-status" className="form-label">
                  Status
                </label>
                <select
                  id="workflow-status"
                  value={workflow.status || 'draft'}
                  onChange={(e) => onPropertyChange('status', e.target.value)}
                  className="form-select w-full mt-1"
                >
                  <option value="draft">Draft</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="archived">Archived</option>
                </select>
              </div>

              <div>
                <label htmlFor="workflow-trigger" className="form-label">
                  Trigger Type
                </label>
                <select
                  id="workflow-trigger"
                  value={workflow.trigger_type || 'manual'}
                  onChange={(e) => handleTriggerSelect(e.target.value)}
                  className="form-select w-full mt-1"
                >
                  <option value="manual">Manual</option>
                  <option value="webhook">Webhook</option>
                  <option value="schedule">Schedule</option>
                  <option value="event">Event</option>
                  <option value="api">API</option>
                </select>
                <p className="form-helper">
                  How this workflow will be triggered
                </p>
              </div>

              {/* Webhook URL controls */}
              {workflow.trigger_type === 'webhook' && (
                <WebhookConfigSection
                  webhook={webhook}
                  webhookToken={workflow.webhook_token}
                  webhookSecret={workflow.webhook_secret}
                  onMethodChange={onMethodChange}
                  onRegenerateToken={onRegenerateToken}
                />
              )}

              <div className="md:col-span-2">
                <label htmlFor="workflow-description" className="form-label">
                  Description
                </label>
                <textarea
                  id="workflow-description"
                  rows={2}
                  className="form-textarea mt-1"
                  value={workflow.description}
                  onChange={(e) => onPropertyChange('description', e.target.value)}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      <TriggerChangeModal
        isOpen={showTriggerModal}
        onClose={() => {
          setShowTriggerModal(false);
          setPendingTriggerType(null);
        }}
        onConfirm={async () => {
          if (pendingTriggerType) {
            await onTriggerChange(pendingTriggerType);
          }
          setShowTriggerModal(false);
          setPendingTriggerType(null);
        }}
      />
    </>
  );
}
