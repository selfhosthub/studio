// ui/widgets/flow-editor/hooks/useFlowLayout.ts

import { useCallback, useEffect, useRef, useState } from 'react';
import { useReactFlow } from '@xyflow/react';
import { MOBILE_BREAKPOINT, FIT_VIEW_DURATION, MOBILE_HEIGHT_THRESHOLD } from '../constants';
import { TIMEOUTS } from '@/shared/lib/constants';
import type { Step } from '../types';

interface LayoutPreferences {
  nodeWidth: 'narrow' | 'normal' | 'wide';
  nodeSpacing: 'compact' | 'normal' | 'spacious';
}

interface UseFlowLayoutProps {
  steps: Step[];
  preferences: LayoutPreferences;
  calculateLayout: (steps: Step[]) => Step[];
  onStepsChange?: (steps: Step[]) => void;
  onFitViewRef?: (fn: () => void) => void;
  onAutoArrangeRef?: (fn: () => void) => void;
}

interface UseFlowLayoutReturn {
  isInteractive: boolean;
  setIsInteractive: (value: boolean) => void;
  isMobile: boolean;
  isDarkMode: boolean;
  autoArrangeFnRef: React.MutableRefObject<(() => void) | null>;
}

const getIsMobile = () => {
  if (typeof window === 'undefined') return false;
  return (
    window.innerWidth < MOBILE_BREAKPOINT || window.innerHeight < MOBILE_HEIGHT_THRESHOLD
  );
};

/**
 * Hook to manage ReactFlow viewport concerns:
 *   - fit-view (initial + on-demand)
 *   - auto-arrange (calls calculateLayout then fits view)
 *   - preference-driven re-layout when node width / spacing changes
 *   - mobile interactivity toggle
 *   - dark mode detection for grid color
 */
export function useFlowLayout({
  steps,
  preferences,
  calculateLayout,
  onStepsChange,
  onFitViewRef,
  onAutoArrangeRef,
}: UseFlowLayoutProps): UseFlowLayoutReturn {
  const { fitView } = useReactFlow();
  const isMobile =
    typeof window !== 'undefined' && window.innerWidth < MOBILE_BREAKPOINT;

  const [isInteractive, setIsInteractive] = useState(() => !getIsMobile());
  const [isDarkMode, setIsDarkMode] = useState(false);

  // Stable refs so callbacks don't recreate on every steps/onStepsChange change
  const stepsRef = useRef(steps);
  const onStepsChangeRef = useRef(onStepsChange);

  useEffect(() => {
    stepsRef.current = steps;
  }, [steps]);

  useEffect(() => {
    onStepsChangeRef.current = onStepsChange;
  }, [onStepsChange]);

  // Ref for auto-arrange so the Controls toolbar always has the latest version
  const autoArrangeFnRef = useRef<(() => void) | null>(null);

  // Expose fitView and autoArrange to parent via callback refs
  useEffect(() => {
    const padding = isMobile ? 0.4 : 0.2;

    if (onFitViewRef) {
      onFitViewRef(() => {
        fitView({ padding, duration: FIT_VIEW_DURATION });
      });
    }

    const handleAutoArrange = () => {
      const layoutedSteps = calculateLayout(stepsRef.current);
      onStepsChangeRef.current?.(layoutedSteps);
      setTimeout(
        () => fitView({ padding, duration: FIT_VIEW_DURATION }),
        TIMEOUTS.LAYOUT_SETTLE,
      );
    };

    autoArrangeFnRef.current = handleAutoArrange;

    if (onAutoArrangeRef) {
      onAutoArrangeRef(handleAutoArrange);
    }
  }, [onFitViewRef, onAutoArrangeRef, fitView, isMobile, calculateLayout]);

  // Re-layout when spacing/width preference changes
  const prevNodeSpacingRef = useRef(preferences.nodeSpacing);
  const prevNodeWidthRef = useRef(preferences.nodeWidth);

  useEffect(() => {
    const spacingChanged = prevNodeSpacingRef.current !== preferences.nodeSpacing;
    const widthChanged = prevNodeWidthRef.current !== preferences.nodeWidth;

    if ((spacingChanged || widthChanged) && onStepsChange && steps.length > 0) {
      const layoutedSteps = calculateLayout(steps);
      onStepsChange(layoutedSteps);
    }

    prevNodeSpacingRef.current = preferences.nodeSpacing;
    prevNodeWidthRef.current = preferences.nodeWidth;
  }, [preferences.nodeSpacing, preferences.nodeWidth, calculateLayout, onStepsChange, steps]);

  // Dark mode detection via class mutation observer
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const checkDarkMode = () => {
      setIsDarkMode(document.documentElement.classList.contains('dark'));
    };
    checkDarkMode();

    const observer = new MutationObserver(checkDarkMode);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });

    return () => observer.disconnect();
  }, []);

  return {
    isInteractive,
    setIsInteractive,
    isMobile,
    isDarkMode,
    autoArrangeFnRef,
  };
}
