// ui/widgets/flow-editor/hooks/useFlowHistory.ts

import { useCallback, useEffect, useRef, useState } from 'react';
import { MAX_HISTORY_ENTRIES, HISTORY_DEBOUNCE_MS } from '../constants';
import type { Step, FlexibleConnection, HistoryState } from '../types';

interface UseFlowHistoryProps {
  steps: Step[];
  connections: FlexibleConnection[];
  onStepsChange?: (steps: Step[]) => void;
  onConnectionsChange?: (connections: FlexibleConnection[]) => void;
}

interface UseFlowHistoryReturn {
  handleUndo: () => void;
  handleRedo: () => void;
  canUndo: boolean;
  canRedo: boolean;
}

/**
 * Hook to manage undo/redo history for the flow editor.
 * Tracks changes to steps and connections and provides undo/redo functionality.
 */
export function useFlowHistory({
  steps,
  connections,
  onStepsChange,
  onConnectionsChange
}: UseFlowHistoryProps): UseFlowHistoryReturn {
  // Use refs to avoid stale closure issues with callbacks
  const historyRef = useRef<HistoryState[]>([]);
  const historyIndexRef = useRef(-1);
  // Counter to skip history updates from undo/redo actions
  // React batches steps+connections updates into a single render, so we only need to skip 1
  const skipHistoryUpdates = useRef(0);
  const lastSavedState = useRef<string>('');
  const isInitialized = useRef(false);
  const historyTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Track undo/redo availability (updated whenever history changes)
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  const syncButtonState = useCallback(() => {
    setCanUndo(historyIndexRef.current > 0);
    setCanRedo(historyIndexRef.current < historyRef.current.length - 1);
  }, []);

  // Initialize history with current state - runs when steps first become available
  useEffect(() => {
    if (!isInitialized.current && steps.length > 0) {
      const initialState: HistoryState = {
        steps: JSON.parse(JSON.stringify(steps)),
        connections: JSON.parse(JSON.stringify(connections))
      };
      historyRef.current = [initialState];
      historyIndexRef.current = 0;
      lastSavedState.current = JSON.stringify({ steps, connections });
      isInitialized.current = true;
      syncButtonState();
    }
  }, [steps, connections, syncButtonState]);

  // Track changes and add to history (debounced to avoid too many snapshots)
  useEffect(() => {
    // Skip if not yet initialized
    if (!isInitialized.current) {
      return;
    }

    // Skip if this is from an undo/redo action (counter decrements each time)
    if (skipHistoryUpdates.current > 0) {
      skipHistoryUpdates.current--;
      return;
    }

    const currentState = JSON.stringify({ steps, connections });

    // Skip if state hasn't changed
    if (currentState === lastSavedState.current) {
      return;
    }

    // Debounce history updates to avoid too many snapshots during rapid changes
    if (historyTimeoutRef.current) {
      clearTimeout(historyTimeoutRef.current);
    }

    historyTimeoutRef.current = setTimeout(() => {
      // Create new history entry with deep copies
      const newEntry: HistoryState = {
        steps: JSON.parse(JSON.stringify(steps)),
        connections: JSON.parse(JSON.stringify(connections))
      };

      // Remove any future history if we're not at the end (for redo after undo then new action)
      const currentIndex = historyIndexRef.current;
      const newHistory = historyRef.current.slice(0, currentIndex + 1);
      // Add new entry (limit entries to prevent memory issues)
      newHistory.push(newEntry);
      if (newHistory.length > MAX_HISTORY_ENTRIES) {
        newHistory.shift();
      }

      historyRef.current = newHistory;
      historyIndexRef.current = newHistory.length - 1;
      lastSavedState.current = currentState;
      syncButtonState();
    }, HISTORY_DEBOUNCE_MS);

    return () => {
      if (historyTimeoutRef.current) {
        clearTimeout(historyTimeoutRef.current);
      }
    };
  }, [steps, connections, syncButtonState]);

  // Undo function
  const handleUndo = useCallback(() => {
    const currentIndex = historyIndexRef.current;

    if (currentIndex > 0 && onStepsChange && onConnectionsChange) {
      // Skip the next history update (React batches the steps+connections into one render)
      skipHistoryUpdates.current = 1;
      const prevIndex = currentIndex - 1;
      const prevState = historyRef.current[prevIndex];

      if (prevState) {
        historyIndexRef.current = prevIndex;
        lastSavedState.current = JSON.stringify(prevState);
        onStepsChange(JSON.parse(JSON.stringify(prevState.steps)));
        onConnectionsChange(JSON.parse(JSON.stringify(prevState.connections)));
        syncButtonState();
      }
    }
  }, [onStepsChange, onConnectionsChange, syncButtonState]);

  // Redo function
  const handleRedo = useCallback(() => {
    const currentIndex = historyIndexRef.current;
    const historyLength = historyRef.current.length;

    if (currentIndex < historyLength - 1 && onStepsChange && onConnectionsChange) {
      // Skip the next history update (React batches the steps+connections into one render)
      skipHistoryUpdates.current = 1;
      const nextIndex = currentIndex + 1;
      const nextState = historyRef.current[nextIndex];

      if (nextState) {
        historyIndexRef.current = nextIndex;
        lastSavedState.current = JSON.stringify(nextState);
        onStepsChange(JSON.parse(JSON.stringify(nextState.steps)));
        onConnectionsChange(JSON.parse(JSON.stringify(nextState.connections)));
        syncButtonState();
      }
    }
  }, [onStepsChange, onConnectionsChange, syncButtonState]);

  // Keyboard shortcuts for undo/redo
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Check if we're in an input field - if so, let browser handle it
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return;
      }

      const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
      const modKey = isMac ? e.metaKey : e.ctrlKey;

      if (modKey && e.key === 'z' && !e.shiftKey) {
        // Cmd/Ctrl + Z = Undo
        e.preventDefault();
        handleUndo();
      } else if (modKey && e.key === 'z' && e.shiftKey) {
        // Cmd/Ctrl + Shift + Z = Redo
        e.preventDefault();
        handleRedo();
      } else if (modKey && e.key === 'y') {
        // Cmd/Ctrl + Y = Redo (Windows style)
        e.preventDefault();
        handleRedo();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleUndo, handleRedo]);

  return {
    handleUndo,
    handleRedo,
    canUndo,
    canRedo
  };
}
