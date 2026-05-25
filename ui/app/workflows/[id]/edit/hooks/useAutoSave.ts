// ui/app/workflows/[id]/edit/hooks/useAutoSave.ts

import { useState, useRef, useEffect, useCallback } from 'react';
import { TIMEOUTS } from '@/shared/lib/constants';

interface UseAutoSaveOptions {
  onSave: () => Promise<void>;
  hasUnsavedChanges: () => boolean;
  enabled?: boolean;
}

export function useAutoSave({ onSave, hasUnsavedChanges, enabled = true }: UseAutoSaveOptions) {
  const [autoSaveInterval, setAutoSaveInterval] = useState<number | null>(() => {
    if (typeof window === 'undefined') return null;
    const saved = window.localStorage.getItem('workflowAutoSaveInterval');
    return saved ? parseInt(saved, 10) : null;
  });
  const [autoSaveCountdown, setAutoSaveCountdown] = useState<number | null>(null);
  const [showAutoSaveDropdown, setShowAutoSaveDropdown] = useState(false);
  const [showCustomAutoSave, setShowCustomAutoSave] = useState(false);
  const [customAutoSaveValue, setCustomAutoSaveValue] = useState('');
  const autoSaveTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (showAutoSaveDropdown && !target.closest('[data-auto-save-dropdown]')) {
        setShowAutoSaveDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showAutoSaveDropdown]);

  const formatCountdown = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  useEffect(() => {
    if (!enabled) return;

    if (autoSaveTimerRef.current) {
      clearInterval(autoSaveTimerRef.current);
    }

    if (autoSaveInterval && autoSaveInterval > 0) {
      let secondsRemaining = autoSaveInterval * 60;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAutoSaveCountdown(secondsRemaining);

      autoSaveTimerRef.current = setInterval(() => {
        secondsRemaining -= 1;
        setAutoSaveCountdown(secondsRemaining);

        if (secondsRemaining <= 0) {
          if (hasUnsavedChanges()) {
            onSave();
          }
          secondsRemaining = autoSaveInterval * 60;
          setAutoSaveCountdown(secondsRemaining);
        }
      }, TIMEOUTS.COUNTDOWN_INTERVAL);
    } else {
      setAutoSaveCountdown(null);
    }

    return () => {
      if (autoSaveTimerRef.current) {
        clearInterval(autoSaveTimerRef.current);
      }
    };
  }, [autoSaveInterval, enabled, hasUnsavedChanges, onSave]);

  useEffect(() => {
    if (autoSaveInterval) {
      localStorage.setItem('workflowAutoSaveInterval', String(autoSaveInterval));
    } else {
      localStorage.removeItem('workflowAutoSaveInterval');
    }
  }, [autoSaveInterval]);

  const handleSetAutoSaveInterval = useCallback((value: number | null) => {
    setAutoSaveInterval(value);
    setShowCustomAutoSave(false);
    setShowAutoSaveDropdown(false);
  }, []);

  const handleCustomAutoSaveSubmit = useCallback(() => {
    const val = parseInt(customAutoSaveValue);
    if (val >= 1 && val <= 120) {
      setAutoSaveInterval(val);
      setShowCustomAutoSave(false);
      setShowAutoSaveDropdown(false);
    }
  }, [customAutoSaveValue]);

  return {
    autoSaveInterval,
    setAutoSaveInterval,
    autoSaveCountdown,
    showAutoSaveDropdown,
    setShowAutoSaveDropdown,
    showCustomAutoSave,
    setShowCustomAutoSave,
    customAutoSaveValue,
    setCustomAutoSaveValue,
    formatCountdown,
    handleSetAutoSaveInterval,
    handleCustomAutoSaveSubmit,
  };
}
