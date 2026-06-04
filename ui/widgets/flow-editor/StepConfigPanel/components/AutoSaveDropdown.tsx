// ui/widgets/flow-editor/StepConfigPanel/components/AutoSaveDropdown.tsx

'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { Save, Clock, ChevronDown, Check } from 'lucide-react';
import { CountdownTimer } from './CountdownTimer';

interface AutoSaveDropdownProps {
  onSave: () => void;
  isSaving?: boolean;
  hasUnsavedChanges?: boolean;
  propAutoSaveInterval?: number | null;
  propAutoSaveCountdown?: number | null;
  onAutoSaveIntervalChange?: (interval: number | null) => void;
}

export function AutoSaveDropdown({
  onSave,
  isSaving,
  hasUnsavedChanges,
  propAutoSaveInterval,
  propAutoSaveCountdown,
  onAutoSaveIntervalChange,
}: AutoSaveDropdownProps) {
  const [showDropdown, setShowDropdown] = useState(false);
  const [showCustom, setShowCustom] = useState(false);
  const [customValue, setCustomValue] = useState('');
  const [localInterval, setLocalInterval] = useState<number | null>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('workflowAutoSaveInterval');
      return saved ? parseInt(saved, 10) : null;
    }
    return null;
  });
  // Track countdown threshold for button styling (only updates on threshold crossings, not every second)
  const [countdownThreshold, setCountdownThreshold] = useState<'normal' | 'warning' | 'urgent'>('normal');

  // Use props if provided, otherwise use local state
  const autoSaveInterval = propAutoSaveInterval !== undefined ? propAutoSaveInterval : localInterval;
  const setAutoSaveInterval = onAutoSaveIntervalChange || setLocalInterval;

  // Determine if we should show countdown (local mode only - when props not provided)
  const showLocalCountdown = propAutoSaveInterval === undefined && localInterval && onSave;

  // Save auto-save interval to localStorage - only when using local state
  useEffect(() => {
    // Skip if using props (parent manages localStorage)
    if (onAutoSaveIntervalChange) return;

    if (typeof window !== 'undefined') {
      if (localInterval) {
        localStorage.setItem('workflowAutoSaveInterval', String(localInterval));
      } else {
        localStorage.removeItem('workflowAutoSaveInterval');
      }
    }
  }, [localInterval, onAutoSaveIntervalChange]);

  // Handle countdown threshold updates (for button color changes)
  const handleCountdownUpdate = useCallback((countdown: number) => {
    if (countdown <= 10) {
      setCountdownThreshold('urgent');
    } else if (countdown <= 60) {
      setCountdownThreshold('warning');
    } else {
      setCountdownThreshold('normal');
    }
  }, []);

  const handleSave = useCallback(() => {
    onSave();
  }, [onSave]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (showDropdown && !target.closest('[data-auto-save-dropdown]')) {
        setShowDropdown(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showDropdown]);

  return (
    <div className="relative flex items-center" data-auto-save-dropdown>
      <button
        onClick={handleSave}
        disabled={isSaving}
        className={`p-1.5 rounded-l-md transition-colors text-white disabled:opacity-50 ${
          hasUnsavedChanges
            ? 'bg-critical hover:bg-[var(--theme-critical)]'
            : 'bg-info hover:bg-[var(--theme-primary)]'
        }`}
        title={hasUnsavedChanges ? 'Save changes (unsaved)' : 'Save workflow'}
      >
        {isSaving ? (
          <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
        ) : (
          <Save size={16} />
        )}
      </button>
      <button
        onClick={() => setShowDropdown(!showDropdown)}
        className={`flex items-center px-1.5 py-1.5 rounded-r-md border-l text-sm transition-colors ${
          countdownThreshold === 'urgent'
            ? 'bg-danger border-danger hover:bg-[var(--theme-danger)] animate-pulse text-white'
            : countdownThreshold === 'warning'
              ? 'bg-critical border-critical hover:bg-[var(--theme-critical)] text-white'
              : 'bg-blue-900 border-blue-800 hover:bg-blue-700 text-cyan-300' // css-check-ignore: no semantic token
        }`}
        title={autoSaveInterval ? `Auto-save every ${autoSaveInterval} min` : 'Configure auto-save'}
      >
        <Clock size={12} />
        {/* Use isolated CountdownTimer to avoid re-rendering entire panel every second */}
        {showLocalCountdown && localInterval && (
          <CountdownTimer
            interval={localInterval}
            onSave={handleSave}
            onCountdownUpdate={handleCountdownUpdate}
          />
        )}
        {/* When using props, show prop countdown (parent manages timer) */}
        {propAutoSaveCountdown !== undefined && propAutoSaveCountdown !== null && (
          <span className="ml-1 text-xs font-mono">
            {Math.floor(propAutoSaveCountdown / 60)}:{(propAutoSaveCountdown % 60).toString().padStart(2, '0')}
          </span>
        )}
        <ChevronDown size={10} className="ml-0.5" />
      </button>

      {/* Auto-save dropdown */}
      {showDropdown && (
        <div className="absolute right-0 top-full mt-1 bg-card border border-primary rounded-md shadow-lg z-50 min-w-[160px]">
          <div className="px-3 py-2 border-b border-secondary">
            <span className="text-xs font-medium text-secondary">Auto-save</span>
          </div>
          {[
            { value: null, label: 'Off' },
            { value: 5, label: '5 minutes' },
            { value: 15, label: '15 minutes' },
            { value: 30, label: '30 minutes' },
          ].map(option => (
            <button
              key={option.value ?? 'off'}
              onClick={() => {
                setAutoSaveInterval(option.value);
                setShowCustom(false);
                setShowDropdown(false);
              }}
              className={`w-full text-left px-3 py-2 text-sm hover:bg-surface flex items-center justify-between ${
                autoSaveInterval === option.value && !showCustom
                  ? 'text-info bg-info-subtle'
                  : 'text-secondary'
              }`}
            >
              {option.label}
              {autoSaveInterval === option.value && !showCustom && <Check size={14} />}
            </button>
          ))}
          {/* Custom option */}
          <div className="border-t border-secondary">
            {showCustom ? (
              <div className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min="1"
                    max="120"
                    value={customValue}
                    onChange={(e) => setCustomValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        const val = parseInt(customValue);
                        if (val >= 1 && val <= 120) {
                          setAutoSaveInterval(val);
                          setShowCustom(false);
                          setShowDropdown(false);
                        }
                      } else if (e.key === 'Escape') {
                        setShowCustom(false);
                        setCustomValue('');
                      }
                    }}
                    placeholder="mins"
                    className="w-16 px-2 py-1 text-sm border border-primary rounded bg-card text-primary"
                    autoFocus
                  />
                  <span className="text-xs text-secondary">min</span>
                  <button
                    type="button"
                    onClick={() => {
                      const val = parseInt(customValue);
                      if (val >= 1 && val <= 120) {
                        setAutoSaveInterval(val);
                        setShowCustom(false);
                        setShowDropdown(false);
                      }
                    }}
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
                  setShowCustom(true);
                  setCustomValue(autoSaveInterval && ![null, 1, 5, 15, 30].includes(autoSaveInterval) ? String(autoSaveInterval) : '');
                }}
                className={`w-full text-left px-3 py-2 text-sm hover:bg-surface flex items-center justify-between ${
                  autoSaveInterval && ![null, 1, 5, 15, 30].includes(autoSaveInterval)
                    ? 'text-info bg-info-subtle'
                    : 'text-secondary'
                }`}
              >
                {autoSaveInterval && ![null, 1, 5, 15, 30].includes(autoSaveInterval)
                  ? `${autoSaveInterval} minutes`
                  : 'Custom...'}
                {autoSaveInterval && ![null, 1, 5, 15, 30].includes(autoSaveInterval) && <Check size={14} />}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
