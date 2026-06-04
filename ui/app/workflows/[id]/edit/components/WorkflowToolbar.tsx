// ui/app/workflows/[id]/edit/components/WorkflowToolbar.tsx

'use client';

import React from 'react';
import { ArrowLeft, Save, ChevronDown, Play, Check, Clock } from 'lucide-react';
import Link from 'next/link';

interface WorkflowToolbarProps {
  autoSave: {
    showAutoSaveDropdown: boolean;
    setShowAutoSaveDropdown: (v: boolean) => void;
    autoSaveCountdown: number | null;
    autoSaveInterval: number | null;
    formatCountdown: (s: number) => string;
    handleSetAutoSaveInterval: (v: number | null) => void;
    showCustomAutoSave: boolean;
    setShowCustomAutoSave: (v: boolean) => void;
    customAutoSaveValue: string;
    setCustomAutoSaveValue: (v: string) => void;
    handleCustomAutoSaveSubmit: () => void;
  };
  hasUnsavedChanges: boolean;
  isSubmitting: boolean;
  isRunning: boolean;
  hasSteps: boolean;
  onSave: (e: React.FormEvent) => void;
  onRun: () => void;
}

export function WorkflowToolbar({
  autoSave,
  hasUnsavedChanges,
  isSubmitting,
  isRunning,
  hasSteps,
  onSave,
  onRun,
}: WorkflowToolbarProps) {
  return (
    <>
      <div className="mb-2 flex justify-between items-center">
        <Link
          href="/workflows/list"
          className="inline-flex items-center text-sm link"
        >
          <ArrowLeft className="h-4 w-4 mr-1" />
          Back to Workflows
        </Link>
        <div className="flex items-center gap-2">
          {/* Save Workflow button with auto-save dropdown */}
          <div className="relative flex items-center" data-auto-save-dropdown>
            <button
              type="button"
              onClick={onSave}
              disabled={isSubmitting}
              // css-check-ignore: save button status visualization
              className={`${
                hasUnsavedChanges
                  ? 'bg-orange-600 hover:bg-orange-700 text-white' // css-check-ignore
                  : 'btn-success-sm'
              } rounded-r-none inline-flex items-center px-3 py-1.5 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors`}
            >
              {isSubmitting ? (
                <>
                  <span className="spinner-sm mr-1.5" />
                  <span className="hidden sm:inline">Saving...</span>
                </>
              ) : (
                <>
                  <Save className="h-3.5 w-3.5 sm:mr-1.5" />
                  <span className="hidden sm:inline">Save</span>
                </>
              )}
            </button>
            {/* Auto-save dropdown trigger */}
            <button
              type="button"
              onClick={() => autoSave.setShowAutoSaveDropdown(!autoSave.showAutoSaveDropdown)}
              // css-check-ignore: auto-save countdown status visualization colors
              className={`inline-flex items-center px-1.5 py-1.5 text-sm rounded-r-md border-l transition-colors ${
                autoSave.autoSaveCountdown !== null && autoSave.autoSaveCountdown <= 10
                  ? 'bg-red-600 border-red-700 hover:bg-red-700 animate-pulse text-white' // css-check-ignore
                  : autoSave.autoSaveCountdown !== null && autoSave.autoSaveCountdown <= 60
                    ? 'bg-orange-700 border-orange-800 hover:bg-orange-700 text-white' // css-check-ignore
                    : hasUnsavedChanges
                      ? 'bg-orange-700 border-orange-800 hover:bg-orange-800 text-orange-200' // css-check-ignore
                      : 'bg-emerald-700 border-emerald-800 hover:bg-emerald-800 text-emerald-200' // css-check-ignore
              }`}
              title={autoSave.autoSaveInterval ? `Auto-save every ${autoSave.autoSaveInterval} min` : 'Configure auto-save'}
            >
              <Clock className="h-3.5 w-3.5" />
              {autoSave.autoSaveCountdown !== null && (
                <span className="ml-1 text-xs font-mono">{autoSave.formatCountdown(autoSave.autoSaveCountdown)}</span>
              )}
              <ChevronDown className="h-3 w-3 ml-0.5" />
            </button>
            {/* Auto-save dropdown menu */}
            {autoSave.showAutoSaveDropdown && (
              <div className="absolute top-full mt-1 bg-card border border-primary rounded-md shadow-lg z-50 min-w-[160px]">
                <div className="px-3 py-2 border-b border-primary">
                  <span className="text-xs font-medium text-muted">Auto-save</span>
                </div>
                {[
                  { value: null, label: 'Off' },
                  { value: 5, label: '5 minutes' },
                  { value: 15, label: '15 minutes' },
                  { value: 30, label: '30 minutes' },
                ].map(option => (
                  <button
                    key={option.value ?? 'off'}
                    type="button"
                    onClick={() => autoSave.handleSetAutoSaveInterval(option.value)}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-surface flex items-center justify-between ${
                      autoSave.autoSaveInterval === option.value && !autoSave.showCustomAutoSave
                        ? 'text-info bg-info-subtle'
                        : 'text-secondary'
                    }`}
                  >
                    {option.label}
                    {autoSave.autoSaveInterval === option.value && !autoSave.showCustomAutoSave && <Check className="h-4 w-4" />}
                  </button>
                ))}
                {/* Custom option */}
                <div className="border-t border-primary">
                  {autoSave.showCustomAutoSave ? (
                    <div className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <input
                          type="number"
                          min="1"
                          max="120"
                          value={autoSave.customAutoSaveValue}
                          onChange={(e) => autoSave.setCustomAutoSaveValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              autoSave.handleCustomAutoSaveSubmit();
                            } else if (e.key === 'Escape') {
                              autoSave.setShowCustomAutoSave(false);
                              autoSave.setCustomAutoSaveValue('');
                            }
                          }}
                          placeholder="mins"
                          className="w-16 px-2 py-1 text-sm border border-secondary rounded bg-input text-primary"
                          autoFocus
                        />
                        <span className="text-xs text-muted">min</span>
                        <button
                          type="button"
                          onClick={() => autoSave.handleCustomAutoSaveSubmit()}
                          className="btn-primary text-xs px-2 py-1"
                        >
                          Set
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        autoSave.setShowCustomAutoSave(true);
                        autoSave.setCustomAutoSaveValue(autoSave.autoSaveInterval && ![1, 5, 15, 30].includes(autoSave.autoSaveInterval) ? String(autoSave.autoSaveInterval) : '');
                      }}
                      className={`w-full text-left px-3 py-2 text-sm hover:bg-surface flex items-center justify-between ${
                        autoSave.autoSaveInterval && ![null, 1, 5, 15, 30].includes(autoSave.autoSaveInterval)
                          ? 'text-info bg-info-subtle'
                          : 'text-secondary'
                      }`}
                    >
                      {autoSave.autoSaveInterval && ![null, 1, 5, 15, 30].includes(autoSave.autoSaveInterval)
                        ? `${autoSave.autoSaveInterval} minutes`
                        : 'Custom...'}
                      {autoSave.autoSaveInterval && ![null, 1, 5, 15, 30].includes(autoSave.autoSaveInterval) && <Check className="h-4 w-4" />}
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onRun}
            disabled={isRunning || !hasSteps}
            className="btn-primary-sm inline-flex items-center whitespace-nowrap"
          >
            <Play className="h-3.5 w-3.5 mr-1.5" />
            {isRunning ? 'Running...' : 'Run'}
          </button>
        </div>
      </div>

      <div className="mb-3">
        <h1 className="text-xl font-bold text-primary">
          Edit Workflow
        </h1>
        <p className="text-muted text-xs">
          Modify your workflow configuration and steps.
        </p>
      </div>
    </>
  );
}
