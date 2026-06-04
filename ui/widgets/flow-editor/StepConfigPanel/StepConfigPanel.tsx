// ui/widgets/flow-editor/StepConfigPanel/StepConfigPanel.tsx

'use client';

import React, { useEffect, useRef, useState, useMemo } from 'react';
import { ErrorBoundary } from '@/shared/ui';
import { Step } from '@/entities/workflow';
import { X, GripVertical, PanelLeftClose, PanelLeft, Play } from 'lucide-react';
import { PreviousStepOutputsPanel } from '@/features/step-config/PreviousStepOutputsPanel';
import { usePreferences } from '@/entities/preferences';
import { getInstanceFormFields } from '@/shared/lib/step-utils';
import { getPrompt } from '@/shared/api';
import { BREAKPOINTS } from '@/shared/lib/constants';
import { AutoSaveDropdown } from './components/AutoSaveDropdown';
import { StepNavigationControls } from './components/StepNavigationControls';

interface StepConfigPanelProps {
  isOpen: boolean;
  step: Step | null;
  onClose: () => void;
  previousSteps: Step[];
  allSteps?: Record<string, Step>;
  mode?: 'workflow' | 'blueprint'; // Controls panel UI (outputs panel, save/run buttons)
  onSelectStep?: (stepId: string) => void; // Callback to select a different step
  // Save workflow props
  onSave?: () => void;
  isSaving?: boolean;
  saveSuccess?: boolean;
  hasUnsavedChanges?: boolean;
  // Auto-save props (synced with edit page)
  autoSaveInterval?: number | null;
  autoSaveCountdown?: number | null;
  onAutoSaveIntervalChange?: (interval: number | null) => void;
  /** Called when the step ID needs to change (e.g., when service is first selected) */
  onStepIdChange?: (oldId: string, newId: string) => void;
  // Run workflow props
  onRun?: () => void;
  isRunning?: boolean;
  /** Step configuration content - injected by the app layer to avoid upward FSD imports */
  stepConfigContent?: React.ReactNode;
}

const MIN_WIDTH = 320; // Minimum panel width (config only)
const MAX_WIDTH = 800; // Maximum panel width (config only)
const DEFAULT_WIDTH = 420; // Default panel width (config only)
const MIN_OUTPUTS_WIDTH = 180; // Minimum outputs panel width
const MAX_OUTPUTS_WIDTH = 500; // Maximum outputs panel width
const DEFAULT_OUTPUTS_WIDTH = 280; // Default outputs panel width
const MOBILE_BREAKPOINT = BREAKPOINTS.MD; // Mobile breakpoint (matches Tailwind md:)

export function StepConfigPanel({
  isOpen,
  step,
  onClose,
  previousSteps,
  allSteps,
  mode = 'workflow',
  onSelectStep,
  onSave,
  isSaving,
  saveSuccess,
  hasUnsavedChanges,
  autoSaveInterval: propAutoSaveInterval,
  autoSaveCountdown: propAutoSaveCountdown,
  onAutoSaveIntervalChange,
  onRun,
  isRunning,
  stepConfigContent,
}: StepConfigPanelProps) {
  const { preferences } = usePreferences();
  const panelRef = useRef<HTMLDivElement>(null);
  const outputsPanelRef = useRef<HTMLDivElement>(null);
  const [isResizing, setIsResizing] = useState(false);
  const [isResizingOutputs, setIsResizingOutputs] = useState(false);

  // Mobile detection - check on mount and resize
  // Consider mobile if either dimension is small (handles landscape phones)
  const [isMobile, setIsMobile] = useState(false);

  // Update mobile state on mount and resize
  useEffect(() => {
    const checkMobile = () => {
      // Mobile if width < 768 OR height < 500 (catches landscape phones)
      const isSmallWidth = window.innerWidth < MOBILE_BREAKPOINT;
      const isSmallHeight = window.innerHeight < 500;
      setIsMobile(isSmallWidth || isSmallHeight);
    };

    // Check immediately on mount
    checkMobile();

    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const [panelWidth, setPanelWidth] = useState(() => {
    // Load saved width from localStorage
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('stepConfigPanelWidth');
      return saved ? parseInt(saved, 10) : DEFAULT_WIDTH;
    }
    return DEFAULT_WIDTH;
  });
  const [outputsPanelWidth, setOutputsPanelWidth] = useState(() => {
    // Load saved outputs panel width from localStorage
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('stepConfigOutputsPanelWidth');
      return saved ? parseInt(saved, 10) : DEFAULT_OUTPUTS_WIDTH;
    }
    return DEFAULT_OUTPUTS_WIDTH;
  });

  // Map blur preference to Tailwind classes
  const getBlurClass = () => {
    switch (preferences.backdropBlur) {
      case 'none':
        return '';
      case 'light':
        return 'backdrop-blur-[2px]';
      case 'heavy':
        return 'backdrop-blur-md';
      default:
        return 'backdrop-blur-[2px]';
    }
  };

  // Handle Escape key and click outside
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    const handleClickOutside = (e: MouseEvent) => {
      if (!isOpen) return;

      const target = e.target as HTMLElement;

      // Don't close if clicking inside the panel
      if (panelRef.current?.contains(target)) {
        return;
      }

      // Don't close if clicking inside the outputs panel
      if (outputsPanelRef.current?.contains(target)) {
        return;
      }

      // Don't close if clicking inside the flow editor
      if (target.closest('.react-flow')) {
        return;
      }

      // Don't close if clicking inside a modal or dialog (portaled content)
      if (target.closest('[role="dialog"]') || target.closest('[data-radix-portal]') || target.closest('.modal')) {
        return;
      }

      // Don't close if clicking inside a step config dropdown (portaled from MappableParameterField)
      if (target.closest('[data-step-config-dropdown]')) {
        return;
      }

      // Don't close if clicking inside the provider docs slide-over
      if (target.closest('[data-provider-docs-panel]') || target.closest('[data-provider-docs-backdrop]')) {
        return;
      }

      onClose();
    };

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, onClose]);

  // Prevent body scroll when panel is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }

    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  // Track outputs panel visibility
  const [showOutputsPanel, setShowOutputsPanel] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('stepConfigShowOutputsPanel');
      return saved !== 'false'; // Default to true
    }
    return true;
  });

  // Handle main panel resize (left edge)
  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      const newWidth = window.innerWidth - e.clientX;
      const clampedWidth = Math.min(Math.max(newWidth, MIN_WIDTH), MAX_WIDTH);
      setPanelWidth(clampedWidth);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      // Save to localStorage
      if (typeof window !== 'undefined') {
        localStorage.setItem('stepConfigPanelWidth', String(panelWidth));
      }
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    // Prevent text selection while resizing
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'ew-resize';

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [isResizing, panelWidth]);

  // Handle outputs panel resize (left edge of separate outputs panel)
  useEffect(() => {
    if (!isResizingOutputs) return;

    const handleMouseMove = (e: MouseEvent) => {
      // Outputs panel is positioned at right: panelWidth, so its left edge is at (window.innerWidth - panelWidth - outputsWidth)
      // New width = (window.innerWidth - panelWidth) - e.clientX
      const outputsPanelRightEdge = window.innerWidth - panelWidth;
      const newWidth = outputsPanelRightEdge - e.clientX;
      const clampedWidth = Math.min(Math.max(newWidth, MIN_OUTPUTS_WIDTH), MAX_OUTPUTS_WIDTH);
      setOutputsPanelWidth(clampedWidth);
    };

    const handleMouseUp = () => {
      setIsResizingOutputs(false);
      // Save to localStorage
      if (typeof window !== 'undefined') {
        localStorage.setItem('stepConfigOutputsPanelWidth', String(outputsPanelWidth));
      }
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    // Prevent text selection while resizing
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'ew-resize';

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [isResizingOutputs, outputsPanelWidth, panelWidth]);

  // Save outputs panel visibility preference
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('stepConfigShowOutputsPanel', String(showOutputsPanel));
    }
  }, [showOutputsPanel]);

  // Fetch prompt variable names for steps with prompt mappings
  // Prompt variables are defined in the Prompt entity, not in input_mappings
  const [promptVarCache, setPromptVarCache] = useState<Record<string, string[]>>({});

  useEffect(() => {
    if (!allSteps) return;
    const promptIdsToFetch: string[] = [];
    for (const s of Object.values(allSteps)) {
      if (!s.input_mappings) continue;
      for (const m of Object.values(s.input_mappings)) {
        if (m.mappingType === 'prompt' && m.promptId && !promptVarCache[m.promptId]) {
          promptIdsToFetch.push(m.promptId);
        }
      }
    }
    if (promptIdsToFetch.length === 0) return;

    let cancelled = false;
    const fetchAll = async () => {
      const newCache: Record<string, string[]> = {};
      await Promise.all(
        [...new Set(promptIdsToFetch)].map(async (tid) => {
          try {
            const prompt = await getPrompt(tid);
            if (prompt?.variables) {
              newCache[tid] = prompt.variables.map((v: any) => v.name);
            }
          } catch { /* prompt may not exist */ }
        })
      );
      if (!cancelled && Object.keys(newCache).length > 0) {
        setPromptVarCache(prev => ({ ...prev, ...newCache }));
      }
    };
    fetchAll();
    return () => { cancelled = true; };
  }, [allSteps, promptVarCache]);

  // Compute instance form fields for mapping (workflow-level runtime inputs)
  // Must be before early return to satisfy Rules of Hooks
  const instanceFormFields = useMemo(() => {
    if (!allSteps) return undefined;
    const stepsArr = Object.values(allSteps);
    if (stepsArr.length === 0) return undefined;
    const fields = getInstanceFormFields(stepsArr, promptVarCache);
    return Object.keys(fields).length > 0 ? fields : undefined;
  }, [allSteps, promptVarCache]);

  if (!isOpen || !step) return null;

  const blurClass = getBlurClass();

  // Check if instance form fields from OTHER steps exist (for showing inputs panel on first step)
  const hasFormFieldsFromOtherSteps = !!(instanceFormFields && step &&
    Object.values(instanceFormFields).some(f => !f._owning_step_ids?.includes(step.id)));

  return (
    <ErrorBoundary name="Step Config">
    <>
      {/* Backdrop - Visual overlay only, click handling is via document listener */}
      <div
        className={`fixed inset-0 bg-black/20 ${blurClass} z-40 transition-opacity duration-300 pointer-events-none`}
        aria-hidden="true"
      />

      {/* Outputs Panel - Separate sliding panel to the left of main panel (desktop only) */}
      {!isMobile && mode === 'workflow' && (previousSteps.length > 0 || hasFormFieldsFromOtherSteps) && (
        <div
          ref={outputsPanelRef}
          style={{
            width: `${outputsPanelWidth}px`,
            right: `${panelWidth}px`,
          }}
          className={`
            fixed top-0 h-full bg-card shadow-xl z-40 border-r border-primary
            transform transition-transform duration-300 ease-out
            ${showOutputsPanel && isOpen ? 'translate-x-0' : 'translate-x-full'}
          `}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Resize handle for outputs panel */}
          <div
            className="absolute left-0 top-0 w-1 h-full cursor-ew-resize hover:bg-[var(--theme-primary)] hover:w-1.5 transition-all group z-20"
            onMouseDown={() => setIsResizingOutputs(true)}
          >
            <div className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1/2 bg-muted group-hover:bg-[var(--theme-primary)] rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
              <GripVertical size={12} className="text-white" />
            </div>
          </div>
          <div className="h-full overflow-y-auto">
            <PreviousStepOutputsPanel
              previousSteps={previousSteps}
              inputMappings={step?.input_mappings as Record<string, { mappingType?: 'mapped' | 'static'; stepId?: string; outputField?: string; source_step_id?: string; source_output_field?: string }> | undefined}
              instanceFormFields={instanceFormFields}
              currentStepId={step?.id}
            />
          </div>
        </div>
      )}

      {/* Slide-out Panel - Higher z-index than backdrop */}
      {/* On mobile: full width, slides up from bottom. On desktop: side panel with custom width */}
      <div
        ref={panelRef}
        style={isMobile ? undefined : { width: `${panelWidth}px` }}
        className={`
          fixed bg-card shadow-2xl z-50
          transform transition-transform duration-300 ease-out
          flex flex-col
          ${isMobile
            ? `inset-x-0 bottom-0 top-12 rounded-t-xl ${isOpen ? 'translate-y-0' : 'translate-y-full'}`
            : `right-0 top-0 h-full ${isOpen ? 'translate-x-0' : 'translate-x-full'}`
          }
        `}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="panel-title"
      >
        {/* Resize Handle - Desktop only */}
        {!isMobile && (
          <div
            className="absolute left-0 top-0 w-1 h-full cursor-ew-resize hover:bg-[var(--theme-primary)] hover:w-1.5 transition-all group z-20"
            onMouseDown={() => setIsResizing(true)}
          >
            <div className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1/2 bg-muted group-hover:bg-[var(--theme-primary)] rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
              <GripVertical size={12} className="text-white" />
            </div>
          </div>
        )}

        {/* Mobile drag handle - swipe down to close */}
        {isMobile && (
          <div
            className="flex-shrink-0 flex justify-center py-2 cursor-grab active:cursor-grabbing"
            onTouchStart={(e) => {
              const startY = e.touches[0].clientY;
              const panel = panelRef.current;
              if (!panel) return;

              const handleTouchMove = (moveEvent: TouchEvent) => {
                const deltaY = moveEvent.touches[0].clientY - startY;
                if (deltaY > 0) {
                  panel.style.transform = `translateY(${deltaY}px)`;
                }
              };

              const handleTouchEnd = (endEvent: TouchEvent) => {
                const deltaY = endEvent.changedTouches[0].clientY - startY;
                panel.style.transform = '';
                // If dragged down more than 100px, close the panel
                if (deltaY > 100) {
                  onClose();
                }
                document.removeEventListener('touchmove', handleTouchMove);
                document.removeEventListener('touchend', handleTouchEnd);
              };

              document.addEventListener('touchmove', handleTouchMove);
              document.addEventListener('touchend', handleTouchEnd);
            }}
          >
            <div className="w-10 h-1 bg-muted rounded-full" />
          </div>
        )}

        {/* Header */}
        <div className="flex-shrink-0 bg-card border-b border-primary px-4 py-2 flex items-center justify-between">
          {/* Left section: Inputs toggle (icon only) */}
          <div className="flex items-center gap-2">
            {/* Toggle outputs panel button - icon only with badge */}
            {mode === 'workflow' && (previousSteps.length > 0 || hasFormFieldsFromOtherSteps) && (
              <button
                type="button"
                onClick={() => setShowOutputsPanel(!showOutputsPanel)}
                className={`relative p-1.5 rounded-md transition-colors ${
                  showOutputsPanel
                    ? 'bg-info-subtle text-info hover:bg-[var(--theme-primary)]/20'
                    : 'bg-card text-secondary hover:bg-input'
                }`}
                aria-label={showOutputsPanel ? 'Hide inputs panel' : 'Show inputs panel'}
                title={showOutputsPanel ? 'Hide previous step outputs' : 'Show previous step outputs'}
              >
                {showOutputsPanel ? <PanelLeftClose size={18} /> : <PanelLeft size={18} />}
                <span className={`absolute -top-1 -right-1 text-[10px] min-w-[16px] h-4 flex items-center justify-center px-1 rounded-full ${
                  showOutputsPanel
                    ? 'bg-info text-white'
                    : 'bg-muted text-white'
                }`}>
                  {previousSteps.length || (hasFormFieldsFromOtherSteps ? Object.values(instanceFormFields!).filter(f => !f._owning_step_ids?.includes(step.id)).length : 0)}
                </span>
              </button>
            )}
          </div>

          {/* Center section: Save + Auto-save */}
          {mode === 'workflow' && onSave && (
            <AutoSaveDropdown
              onSave={onSave}
              isSaving={isSaving}
              hasUnsavedChanges={hasUnsavedChanges}
              propAutoSaveInterval={propAutoSaveInterval}
              propAutoSaveCountdown={propAutoSaveCountdown}
              onAutoSaveIntervalChange={onAutoSaveIntervalChange}
            />
          )}

          {/* Run button - small primary play icon */}
          {mode === 'workflow' && onRun && (
            <button
              onClick={onRun}
              disabled={isRunning}
              className="p-1.5 rounded-md text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ backgroundColor: 'var(--theme-btn-primary-bg)' }}
              title={isRunning ? 'Running...' : 'Run workflow'}
            >
              {isRunning ? (
                <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full block" />
              ) : (
                <Play size={16} />
              )}
            </button>
          )}

          {/* Right section: Step Navigation + Close */}
          <div className="flex items-center gap-2">
            {/* Step Navigation - hidden on mobile for space */}
            {!isMobile && onSelectStep && (
              <StepNavigationControls
                allSteps={allSteps}
                currentStepId={step.id}
                currentStepDependsOn={step.depends_on || []}
                onSelectStep={onSelectStep}
              />
            )}

            {/* Divider between nav and close - hidden on mobile */}
            {!isMobile && <div className="h-4 w-px bg-input mx-2" />}

            {/* ESC hint - hidden on mobile */}
            {!isMobile && (
              <span className="text-xs text-muted dark:text-secondary">
                ESC
              </span>
            )}
            <button
              onClick={onClose}
              className="flex-shrink-0 p-1 rounded-md text-muted hover:text-secondary hover:bg-card transition-colors"
              aria-label="Close panel"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
          {/* Mobile only: Previous Step Outputs Panel as collapsible section at top */}
          {isMobile && mode === 'workflow' && (previousSteps.length > 0 || hasFormFieldsFromOtherSteps) && showOutputsPanel && (
            <div className="border-b border-primary max-h-[40vh] overflow-y-auto flex-shrink-0">
              <PreviousStepOutputsPanel
                previousSteps={previousSteps}
                inputMappings={step.input_mappings as Record<string, { mappingType?: 'mapped' | 'static'; stepId?: string; outputField?: string; source_step_id?: string; source_output_field?: string }> | undefined}
                instanceFormFields={instanceFormFields}
                currentStepId={step.id}
              />
            </div>
          )}

          {/* Main config content */}
          <div className="flex-1 p-4 overflow-y-auto">
            {stepConfigContent}
          </div>
        </div>
      </div>
    </>
    </ErrorBoundary>
  );
}
